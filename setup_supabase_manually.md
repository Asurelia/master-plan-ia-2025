# Configuration manuelle de Supabase

## Étape 1: Créer les tables dans le Dashboard Supabase

1. Allez sur https://supabase.com/dashboard
2. Connectez-vous à votre projet `mtiwjnsseuvwvmfxcrcz`
3. Allez dans l'onglet **SQL Editor**
4. Exécutez le contenu du fichier `sql/create_tables.sql`

## Étape 2: Vérifier la connexion

Une fois les tables créées, exécutez:

```bash
source venv/bin/activate
python3 -c "
import asyncio
import sys
import os
sys.path.append(os.getcwd())
from core.supabase_integration import supabase

async def test():
    health = await supabase.health_check()
    print(f'Health check: {health}')
    
    agents = await supabase.get_agents()
    print(f'Agents: {len(agents)} trouvés')

asyncio.run(test())
"
```

## Étape 3: Tester l'intégration

Le script `core/supabase_integration.py` devrait maintenant fonctionner correctement.

## Note importante

Les clés API Supabase dans ce projet sont des clés publiques `anon` qui permettent uniquement la lecture avec les politiques RLS. Pour des opérations DDL (CREATE TABLE), il faut utiliser le Dashboard ou une clé service avec plus de permissions.