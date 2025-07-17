#!/usr/bin/env python3
"""
Master Plan IA 2025 - Security Validation Script
Vérifie que la configuration de sécurité est correcte
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Tuple

# Ajouter le chemin core au PYTHONPATH
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'core'))

class SecurityValidator:
    """Validateur de sécurité pour Master Plan IA"""
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.info = []
        
    def check_environment_variables(self) -> bool:
        """Vérifie les variables d'environnement critiques"""
        print("🔍 Vérification des variables d'environnement...")
        
        critical_vars = {
            'JWT_SECRET_KEY': 'Clé secrète JWT pour l\'authentification',
            'ENCRYPTION_KEY': 'Clé de chiffrement pour les données sensibles'
        }
        
        important_vars = {
            'SUPABASE_URL': 'URL du projet Supabase',
            'SUPABASE_ANON_KEY': 'Clé anonyme Supabase',
            'ENVIRONMENT': 'Environnement (development/staging/production)'
        }
        
        # Vérifier les variables critiques
        for var, desc in critical_vars.items():
            if not os.getenv(var):
                # Vérifier si un fichier secret existe
                secret_file = Path(f'.secrets/{var.lower()}.key')
                if secret_file.exists():
                    self.warnings.append(f"⚠️  {var} non défini - utilisation du fichier {secret_file}")
                else:
                    self.errors.append(f"❌ {var} manquant - {desc}")
        
        # Vérifier les variables importantes
        for var, desc in important_vars.items():
            if not os.getenv(var):
                self.warnings.append(f"⚠️  {var} non défini - {desc}")
        
        return len(self.errors) == 0
    
    def check_secure_config(self) -> bool:
        """Vérifie la configuration sécurisée"""
        print("🔍 Vérification de la configuration sécurisée...")
        
        try:
            from secure_config import secure_config
            
            # Valider la configuration
            validation = secure_config.validate_configuration()
            
            for check, passed in validation.items():
                if passed:
                    self.info.append(f"✅ {check}")
                else:
                    self.errors.append(f"❌ {check} échoué")
            
            # Vérifications supplémentaires
            if secure_config.is_production():
                if secure_config.is_debug():
                    self.errors.append("❌ DEBUG activé en production!")
                
                if not secure_config.app_config.https_redirect_enabled:
                    self.errors.append("❌ HTTPS non forcé en production!")
                
                if '*' in secure_config.app_config.allowed_origins:
                    self.errors.append("❌ CORS wildcard (*) en production!")
            
            return True
            
        except Exception as e:
            self.errors.append(f"❌ Impossible de charger secure_config: {e}")
            return False
    
    def check_file_permissions(self) -> bool:
        """Vérifie les permissions des fichiers sensibles"""
        print("🔍 Vérification des permissions de fichiers...")
        
        sensitive_paths = [
            '.env',
            '.secrets',
            'config/supabase.yaml',
            '.secrets/jwt_secret_key.key',
            '.secrets/encryption_key.key'
        ]
        
        for path_str in sensitive_paths:
            path = Path(path_str)
            if path.exists():
                if path.is_file():
                    # Vérifier les permissions du fichier
                    mode = oct(path.stat().st_mode)[-3:]
                    if mode != '600':
                        self.warnings.append(f"⚠️  {path} a des permissions {mode} (recommandé: 600)")
                elif path.is_dir():
                    # Vérifier les permissions du dossier
                    mode = oct(path.stat().st_mode)[-3:]
                    if mode != '700':
                        self.warnings.append(f"⚠️  {path} a des permissions {mode} (recommandé: 700)")
        
        return True
    
    def check_dependencies(self) -> bool:
        """Vérifie les dépendances de sécurité"""
        print("🔍 Vérification des dépendances...")
        
        required_packages = {
            'cryptography': 'Chiffrement des données',
            'python-jose': 'JWT tokens',
            'passlib': 'Hashing des mots de passe',
            'python-multipart': 'Upload de fichiers sécurisé'
        }
        
        for package, desc in required_packages.items():
            try:
                __import__(package.replace('-', '_'))
                self.info.append(f"✅ {package} installé - {desc}")
            except ImportError:
                self.warnings.append(f"⚠️  {package} non installé - {desc}")
        
        return True
    
    def check_api_endpoints(self) -> bool:
        """Vérifie la sécurité des endpoints API"""
        print("🔍 Vérification des endpoints API...")
        
        try:
            # Lire le fichier API pour analyser
            api_file = Path('api/unified_api.py')
            if api_file.exists():
                content = api_file.read_text()
                
                # Vérifications basiques
                if 'allow_origins=["*"]' in content:
                    self.errors.append("❌ CORS wildcard trouvé dans l'API!")
                
                if 'HTTPBearer(auto_error=False)' in content:
                    self.info.append("✅ Authentification JWT configurée")
                
                if 'require_admin' in content:
                    self.info.append("✅ Protection admin implémentée")
                
                if 'create_defensive_middleware_stack' in content:
                    self.info.append("✅ Middleware défensif appliqué")
            
            return True
            
        except Exception as e:
            self.warnings.append(f"⚠️  Impossible de vérifier l'API: {e}")
            return True
    
    def generate_report(self) -> Dict[str, any]:
        """Génère un rapport de sécurité"""
        return {
            'timestamp': str(Path(__file__).stat().st_mtime),
            'errors': len(self.errors),
            'warnings': len(self.warnings),
            'passed': len(self.errors) == 0,
            'details': {
                'errors': self.errors,
                'warnings': self.warnings,
                'info': self.info
            }
        }
    
    def run_all_checks(self) -> bool:
        """Exécute toutes les vérifications"""
        print("\n🛡️  VALIDATION DE SÉCURITÉ - MASTER PLAN IA 2025")
        print("=" * 50)
        
        checks = [
            self.check_environment_variables,
            self.check_secure_config,
            self.check_file_permissions,
            self.check_dependencies,
            self.check_api_endpoints
        ]
        
        all_passed = True
        for check in checks:
            if not check():
                all_passed = False
            print()
        
        # Afficher le résumé
        print("=" * 50)
        print("📊 RÉSUMÉ:")
        print(f"   Erreurs: {len(self.errors)}")
        print(f"   Avertissements: {len(self.warnings)}")
        print(f"   Infos: {len(self.info)}")
        print()
        
        # Afficher les erreurs
        if self.errors:
            print("❌ ERREURS CRITIQUES:")
            for error in self.errors:
                print(f"   {error}")
            print()
        
        # Afficher les avertissements
        if self.warnings:
            print("⚠️  AVERTISSEMENTS:")
            for warning in self.warnings:
                print(f"   {warning}")
            print()
        
        # Verdict final
        if len(self.errors) == 0:
            print("✅ VALIDATION RÉUSSIE - Configuration sécurisée")
        else:
            print("❌ VALIDATION ÉCHOUÉE - Corriger les erreurs avant production")
        
        return len(self.errors) == 0


def main():
    """Point d'entrée principal"""
    validator = SecurityValidator()
    
    # Exécuter toutes les vérifications
    passed = validator.run_all_checks()
    
    # Générer le rapport
    report = validator.generate_report()
    
    # Sauvegarder le rapport
    report_file = Path('security_validation_report.json')
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n📄 Rapport sauvegardé dans: {report_file}")
    
    # Code de sortie
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()