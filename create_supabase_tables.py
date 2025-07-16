#!/usr/bin/env python3
"""
Script pour créer les tables Supabase
"""

import asyncio
import sys
import os
from pathlib import Path

# Ajouter le répertoire racine au path Python
sys.path.append(str(Path(__file__).parent))

from supabase import create_client, Client

async def create_tables():
    """Crée les tables dans Supabase"""
    
    print("🔗 Création des tables Supabase...")
    
    # Configuration
    project_url = 'https://mtiwjnsseuvwvmfxcrcz.supabase.co'
    anon_key = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im10aXdqbnNzZXV2d3ZtZnhjcmN6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTI2NzQ3NzksImV4cCI6MjA2ODI1MDc3OX0.-nrcK6mqaORgdv3rj_5lg-2Tk6VecPJmkZSxBRYOYX8'
    
    try:
        # Créer le client
        client = create_client(project_url, anon_key)
        print("✅ Client Supabase créé avec succès")
        
        # Lire le fichier SQL
        sql_file = Path("sql/create_tables.sql")
        if not sql_file.exists():
            print("❌ Fichier SQL non trouvé: sql/create_tables.sql")
            return False
            
        with open(sql_file, 'r') as f:
            sql_content = f.read()
        
        print(f"📝 Fichier SQL lu: {len(sql_content)} caractères")
        
        # Diviser le SQL en requêtes individuelles
        sql_statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]
        print(f"🔧 {len(sql_statements)} requêtes SQL à exécuter")
        
        success_count = 0
        error_count = 0
        
        for i, statement in enumerate(sql_statements):
            if not statement:
                continue
                
            try:
                # Exécuter la requête via l'API REST
                result = client.rpc('exec_sql', {'query': statement}).execute()
                success_count += 1
                print(f"✅ Requête {i+1}/{len(sql_statements)} exécutée avec succès")
                
            except Exception as e:
                error_count += 1
                print(f"⚠️ Erreur requête {i+1}: {e}")
                
                # Continuer même en cas d'erreur (par exemple, si la table existe déjà)
                if "already exists" in str(e).lower():
                    print("   → Table existe déjà, continuons...")
                elif "relation" in str(e).lower() and "does not exist" in str(e).lower():
                    print("   → Relation manquante, continuons...")
                else:
                    print(f"   → Erreur: {e}")
        
        print(f"\n📊 Résultats:")
        print(f"   ✅ Succès: {success_count}")
        print(f"   ⚠️ Erreurs: {error_count}")
        
        if success_count > 0:
            print("🎉 Tables créées avec succès!")
            return True
        else:
            print("❌ Aucune table créée")
            return False
            
    except Exception as e:
        print(f"❌ Erreur générale: {e}")
        return False

if __name__ == '__main__':
    success = asyncio.run(create_tables())
    if success:
        print("✅ Script terminé avec succès")
    else:
        print("❌ Script terminé avec des erreurs")