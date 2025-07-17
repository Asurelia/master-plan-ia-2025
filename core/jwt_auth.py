#!/usr/bin/env python3
"""
Master Plan IA 2025 - Authentification JWT avec Supabase
Système d'authentification complet avec JWT et intégration Supabase
"""

import asyncio
import jwt
import hashlib
import secrets
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union
from pathlib import Path
import os
import json

# Imports pour FastAPI
from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr

# Import de notre intégration Supabase
from core.supabase_integration import supabase

logger = logging.getLogger(__name__)

class UserCreate(BaseModel):
    """Modèle pour créer un utilisateur"""
    email: EmailStr
    password: str
    role: str = "user"
    profile: Dict[str, Any] = {}

class UserLogin(BaseModel):
    """Modèle pour la connexion"""
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    """Modèle de réponse utilisateur"""
    id: str
    email: str
    role: str
    profile: Dict[str, Any]
    is_active: bool
    created_at: str
    last_login: Optional[str] = None

class TokenResponse(BaseModel):
    """Modèle de réponse token"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse

class JWTAuth:
    """Gestionnaire d'authentification JWT avec Supabase"""
    
    def __init__(self, 
                 jwt_secret: str = None,
                 jwt_algorithm: str = "HS256",
                 access_token_expire_minutes: int = 30,
                 refresh_token_expire_days: int = 30):
        
        self.jwt_secret = jwt_secret or self._get_jwt_secret()
        self.jwt_algorithm = jwt_algorithm
        self.access_token_expire_minutes = access_token_expire_minutes
        self.refresh_token_expire_days = refresh_token_expire_days
        
        # Statistiques
        self.stats = {
            'tokens_generated': 0,
            'tokens_validated': 0,
            'login_attempts': 0,
            'login_success': 0,
            'login_failed': 0,
            'users_created': 0,
            'last_activity': None
        }
        
        # Bearer token scheme pour FastAPI
        self.bearer_scheme = HTTPBearer(auto_error=False)
        
        logger.info("🔐 JWT Auth initialized")
    
    def _get_jwt_secret(self) -> str:
        """Obtient le secret JWT de manière sécurisée"""
        
        # Essayer d'utiliser le système de configuration sécurisé
        try:
            from .secure_config import secure_config
            jwt_config = secure_config.get_jwt_config()
            return jwt_config['secret_key']
        except Exception as e:
            logger.warning(f"Could not load JWT secret from config: {e}")
        
        # Essayer les variables d'environnement
        secret = os.getenv('JWT_SECRET')
        if secret:
            return secret
        
        # Générer un secret aléatoire (SÉCURISÉ - sans logging)
        secret = secrets.token_urlsafe(32)
        logger.warning("Generated new JWT secret - IMPORTANT: Set JWT_SECRET_KEY environment variable for production")
        
        # Sauvegarder de manière sécurisée pour le développement
        try:
            secrets_dir = Path('.secrets')
            secrets_dir.mkdir(mode=0o700, exist_ok=True)
            secret_file = secrets_dir / 'jwt_secret_key.key'
            secret_file.write_text(secret)
            secret_file.chmod(0o600)
            logger.info(f"JWT secret saved to {secret_file} (development only)")
        except Exception as e:
            logger.error(f"Failed to save JWT secret: {e}")
        
        return secret
    
    def _hash_password(self, password: str) -> str:
        """Hash un mot de passe"""
        salt = secrets.token_hex(16)
        password_hash = hashlib.pbkdf2_hmac('sha256', 
                                          password.encode('utf-8'), 
                                          salt.encode('utf-8'), 
                                          100000)
        return f"{salt}:{password_hash.hex()}"
    
    def _verify_password(self, password: str, hashed_password: str) -> bool:
        """Vérifie un mot de passe"""
        try:
            salt, password_hash = hashed_password.split(':')
            return hashlib.pbkdf2_hmac('sha256', 
                                     password.encode('utf-8'), 
                                     salt.encode('utf-8'), 
                                     100000).hex() == password_hash
        except Exception as e:
            logger.error(f"Password verification error: {e}")
            return False
    
    def _create_access_token(self, data: Dict[str, Any]) -> str:
        """Crée un token d'accès JWT"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)
        to_encode.update({"exp": expire, "type": "access"})
        
        encoded_jwt = jwt.encode(to_encode, self.jwt_secret, algorithm=self.jwt_algorithm)
        self.stats['tokens_generated'] += 1
        
        return encoded_jwt
    
    def _create_refresh_token(self, data: Dict[str, Any]) -> str:
        """Crée un token de rafraîchissement"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=self.refresh_token_expire_days)
        to_encode.update({"exp": expire, "type": "refresh"})
        
        return jwt.encode(to_encode, self.jwt_secret, algorithm=self.jwt_algorithm)
    
    def _decode_token(self, token: str) -> Dict[str, Any]:
        """Décode un token JWT"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            self.stats['tokens_validated'] += 1
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.JWTError as e:
            raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
    
    async def register_user(self, user_data: UserCreate) -> Dict[str, Any]:
        """Enregistre un nouvel utilisateur"""
        try:
            # Vérifier si l'utilisateur existe déjà
            existing_users = await supabase.client.table('users').select('*').eq('email', user_data.email).execute()
            if existing_users.data:
                raise HTTPException(status_code=400, detail="User already exists")
            
            # Hasher le mot de passe
            password_hash = self._hash_password(user_data.password)
            
            # Créer l'utilisateur
            user_record = {
                'email': user_data.email,
                'password_hash': password_hash,
                'role': user_data.role,
                'profile': user_data.profile,
                'is_active': True,
                'created_at': datetime.utcnow().isoformat(),
                'updated_at': datetime.utcnow().isoformat()
            }
            
            result = await supabase.client.table('users').insert(user_record).execute()
            
            if result.data:
                self.stats['users_created'] += 1
                user = result.data[0]
                
                # Créer le token d'accès
                access_token = self._create_access_token({
                    "sub": user['id'],
                    "email": user['email'],
                    "role": user['role']
                })
                
                return {
                    'success': True,
                    'user': UserResponse(
                        id=user['id'],
                        email=user['email'],
                        role=user['role'],
                        profile=user['profile'],
                        is_active=user['is_active'],
                        created_at=user['created_at']
                    ),
                    'access_token': access_token,
                    'token_type': 'bearer',
                    'expires_in': self.access_token_expire_minutes * 60
                }
            
            raise HTTPException(status_code=500, detail="User creation failed")
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Registration error: {e}")
            raise HTTPException(status_code=500, detail="Registration failed")
    
    async def authenticate_user(self, credentials: UserLogin) -> Dict[str, Any]:
        """Authentifie un utilisateur"""
        self.stats['login_attempts'] += 1
        
        try:
            # Récupérer l'utilisateur
            result = await supabase.client.table('users').select('*').eq('email', credentials.email).execute()
            
            if not result.data:
                self.stats['login_failed'] += 1
                raise HTTPException(status_code=401, detail="Invalid credentials")
            
            user = result.data[0]
            
            # Vérifier le mot de passe
            if not self._verify_password(credentials.password, user['password_hash']):
                self.stats['login_failed'] += 1
                raise HTTPException(status_code=401, detail="Invalid credentials")
            
            # Vérifier si l'utilisateur est actif
            if not user['is_active']:
                self.stats['login_failed'] += 1
                raise HTTPException(status_code=401, detail="Account inactive")
            
            # Mettre à jour la dernière connexion
            await supabase.client.table('users').update({
                'last_login': datetime.utcnow().isoformat(),
                'updated_at': datetime.utcnow().isoformat()
            }).eq('id', user['id']).execute()
            
            # Créer les tokens
            access_token = self._create_access_token({
                "sub": user['id'],
                "email": user['email'],
                "role": user['role']
            })
            
            refresh_token = self._create_refresh_token({
                "sub": user['id'],
                "email": user['email']
            })
            
            # Enregistrer la session
            session_data = {
                'user_id': user['id'],
                'token': access_token,
                'expires_at': (datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)).isoformat(),
                'created_at': datetime.utcnow().isoformat()
            }
            
            await supabase.client.table('sessions').insert(session_data).execute()
            
            self.stats['login_success'] += 1
            self.stats['last_activity'] = datetime.utcnow().isoformat()
            
            return {
                'success': True,
                'access_token': access_token,
                'refresh_token': refresh_token,
                'token_type': 'bearer',
                'expires_in': self.access_token_expire_minutes * 60,
                'user': UserResponse(
                    id=user['id'],
                    email=user['email'],
                    role=user['role'],
                    profile=user['profile'],
                    is_active=user['is_active'],
                    created_at=user['created_at'],
                    last_login=datetime.utcnow().isoformat()
                )
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            self.stats['login_failed'] += 1
            raise HTTPException(status_code=500, detail="Authentication failed")
    
    async def get_current_user(self, credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())) -> Dict[str, Any]:
        """Récupère l'utilisateur actuel à partir du token"""
        
        if not credentials:
            raise HTTPException(status_code=401, detail="Token missing")
        
        try:
            # Décoder le token
            payload = self._decode_token(credentials.credentials)
            
            # Vérifier le type de token
            if payload.get("type") != "access":
                raise HTTPException(status_code=401, detail="Invalid token type")
            
            user_id = payload.get("sub")
            if not user_id:
                raise HTTPException(status_code=401, detail="Invalid token payload")
            
            # Récupérer l'utilisateur
            result = await supabase.client.table('users').select('*').eq('id', user_id).execute()
            
            if not result.data:
                raise HTTPException(status_code=401, detail="User not found")
            
            user = result.data[0]
            
            if not user['is_active']:
                raise HTTPException(status_code=401, detail="Account inactive")
            
            return {
                'id': user['id'],
                'email': user['email'],
                'role': user['role'],
                'profile': user['profile'],
                'is_active': user['is_active'],
                'created_at': user['created_at'],
                'last_login': user['last_login']
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            raise HTTPException(status_code=401, detail="Invalid token")
    
    async def logout_user(self, credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())) -> Dict[str, Any]:
        """Déconnecte un utilisateur"""
        
        if not credentials:
            raise HTTPException(status_code=401, detail="Token missing")
        
        try:
            # Décoder le token pour récupérer l'utilisateur
            payload = self._decode_token(credentials.credentials)
            user_id = payload.get("sub")
            
            # Supprimer la session
            await supabase.client.table('sessions').delete().eq('token', credentials.credentials).execute()
            
            return {'success': True, 'message': 'Logged out successfully'}
            
        except Exception as e:
            logger.error(f"Logout error: {e}")
            raise HTTPException(status_code=500, detail="Logout failed")
    
    def require_role(self, required_role: str):
        """Décorateur pour vérifier le rôle de l'utilisateur"""
        
        async def role_checker(current_user: Dict[str, Any] = Depends(self.get_current_user)):
            if current_user['role'] != required_role and current_user['role'] != 'admin':
                raise HTTPException(status_code=403, detail="Insufficient permissions")
            return current_user
        
        return role_checker
    
    def require_roles(self, required_roles: List[str]):
        """Décorateur pour vérifier plusieurs rôles"""
        
        async def roles_checker(current_user: Dict[str, Any] = Depends(self.get_current_user)):
            if current_user['role'] not in required_roles and current_user['role'] != 'admin':
                raise HTTPException(status_code=403, detail="Insufficient permissions")
            return current_user
        
        return roles_checker
    
    async def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        """Rafraîchit un token d'accès"""
        
        try:
            payload = self._decode_token(refresh_token)
            
            if payload.get("type") != "refresh":
                raise HTTPException(status_code=401, detail="Invalid token type")
            
            user_id = payload.get("sub")
            email = payload.get("email")
            
            # Vérifier que l'utilisateur existe toujours
            result = await supabase.client.table('users').select('*').eq('id', user_id).execute()
            
            if not result.data:
                raise HTTPException(status_code=401, detail="User not found")
            
            user = result.data[0]
            
            # Créer un nouveau token d'accès
            new_access_token = self._create_access_token({
                "sub": user['id'],
                "email": user['email'],
                "role": user['role']
            })
            
            return {
                'success': True,
                'access_token': new_access_token,
                'token_type': 'bearer',
                'expires_in': self.access_token_expire_minutes * 60
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            raise HTTPException(status_code=401, detail="Token refresh failed")
    
    async def get_user_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        """Récupère les sessions actives d'un utilisateur"""
        
        try:
            result = await supabase.client.table('sessions').select('*').eq('user_id', user_id).execute()
            
            # Filtrer les sessions expirées
            active_sessions = []
            current_time = datetime.utcnow()
            
            for session in result.data:
                expires_at = datetime.fromisoformat(session['expires_at'].replace('Z', '+00:00'))
                if expires_at > current_time:
                    active_sessions.append(session)
            
            return active_sessions
            
        except Exception as e:
            logger.error(f"Get sessions error: {e}")
            return []
    
    async def cleanup_expired_sessions(self):
        """Nettoie les sessions expirées"""
        
        try:
            current_time = datetime.utcnow().isoformat()
            
            result = await supabase.client.table('sessions').delete().lt('expires_at', current_time).execute()
            
            logger.info(f"Cleaned up {len(result.data) if result.data else 0} expired sessions")
            
        except Exception as e:
            logger.error(f"Session cleanup error: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques d'authentification"""
        return {
            **self.stats,
            'success_rate': (self.stats['login_success'] / max(self.stats['login_attempts'], 1)) * 100,
            'active_sessions': 0  # TODO: compter les sessions actives
        }

# Instance globale
jwt_auth = JWTAuth()

# Dépendances FastAPI
def get_current_user():
    """Dépendance pour obtenir l'utilisateur actuel"""
    return Depends(jwt_auth.get_current_user)

def require_admin():
    """Dépendance pour vérifier le rôle admin"""
    return Depends(jwt_auth.require_role("admin"))

def require_user():
    """Dépendance pour vérifier le rôle user ou admin"""
    return Depends(jwt_auth.require_roles(["user", "admin"]))

# Exemple d'utilisation
async def main():
    """Test du système d'authentification"""
    
    print("🔐 Test du système d'authentification JWT")
    print("=" * 50)
    
    # Test d'enregistrement
    print("\n1. Test d'enregistrement...")
    user_data = UserCreate(
        email="test@example.com",
        password="test123",
        role="user",
        profile={"name": "Test User"}
    )
    
    try:
        result = await jwt_auth.register_user(user_data)
        print(f"✅ Utilisateur créé: {result['user'].email}")
        
        # Test de connexion
        print("\n2. Test de connexion...")
        login_data = UserLogin(email="test@example.com", password="test123")
        
        auth_result = await jwt_auth.authenticate_user(login_data)
        print(f"✅ Connexion réussie: {auth_result['user'].email}")
        
        # Test de validation de token
        print("\n3. Test de validation de token...")
        from fastapi.security import HTTPAuthorizationCredentials
        
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=auth_result['access_token']
        )
        
        user = await jwt_auth.get_current_user(credentials)
        print(f"✅ Token valide pour: {user['email']}")
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
    
    # Statistiques
    stats = jwt_auth.get_stats()
    print(f"\n📊 Statistiques: {json.dumps(stats, indent=2)}")

if __name__ == "__main__":
    asyncio.run(main())