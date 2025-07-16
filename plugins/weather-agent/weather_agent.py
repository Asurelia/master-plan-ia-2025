#!/usr/bin/env python3
"""
Plugin Weather Agent - Agent météorologique intelligent
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import logging

# Import du système de plugins
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'core'))

from plugin_system import AgentPlugin, plugin_hook, requires_permission

logger = logging.getLogger(__name__)

class WeatherAgent(AgentPlugin):
    """Agent intelligent pour les données météorologiques"""
    
    PLUGIN_NAME = "weather-agent"
    PLUGIN_VERSION = "1.0.0"
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.api_key = config.get('api_key', '')
        self.default_city = config.get('default_city', 'Paris')
        self.update_interval = config.get('update_interval', 300)
        self.temperature_unit = config.get('temperature_unit', 'celsius')
        
        # Cache local des données météo
        self.weather_cache: Dict[str, Dict[str, Any]] = {}
        self.cache_timestamps: Dict[str, float] = {}
        
        # Statistiques
        self.stats = {
            'requests_made': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'cities_tracked': 0,
            'last_update': None
        }
    
    async def initialize(self) -> bool:
        """Initialise l'agent météo"""
        try:
            logger.info(f"🌤️ Initializing Weather Agent...")
            
            # Valider la configuration
            if not self.api_key:
                logger.warning("⚠️ No API key provided, using mock data")
            
            # Préchauffer le cache avec la ville par défaut
            await self.get_weather(self.default_city)
            
            self.is_initialized = True
            logger.info(f"✅ Weather Agent initialized for {self.default_city}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Weather Agent: {e}")
            return False
    
    async def shutdown(self) -> bool:
        """Arrête l'agent proprement"""
        logger.info("🛑 Shutting down Weather Agent...")
        self.weather_cache.clear()
        self.cache_timestamps.clear()
        return True
    
    @requires_permission('api_calls')
    async def create_agent(self, agent_config: Dict[str, Any]) -> Any:
        """Crée une instance d'agent météo"""
        return self
    
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Exécute une tâche météorologique"""
        task_type = task.get('type', 'get_weather')
        
        if task_type == 'get_weather':
            city = task.get('city', self.default_city)
            weather_data = await self.get_weather(city)
            
            return {
                'success': True,
                'result': weather_data,
                'timestamp': datetime.now().isoformat()
            }
        
        elif task_type == 'get_forecast':
            city = task.get('city', self.default_city)
            days = task.get('days', 5)
            forecast_data = await self.get_forecast(city, days)
            
            return {
                'success': True,
                'result': forecast_data,
                'timestamp': datetime.now().isoformat()
            }
        
        elif task_type == 'analyze_weather':
            city = task.get('city', self.default_city)
            analysis = await self.analyze_weather_pattern(city)
            
            return {
                'success': True,
                'result': analysis,
                'timestamp': datetime.now().isoformat()
            }
        
        else:
            return {
                'success': False,
                'error': f'Unknown task type: {task_type}',
                'timestamp': datetime.now().isoformat()
            }
    
    @requires_permission('internet_access')
    async def get_weather(self, city: str) -> Dict[str, Any]:
        """Récupère les données météo actuelles pour une ville"""
        
        # Vérifier le cache
        cache_key = f"current_{city.lower()}"
        if self._is_cache_valid(cache_key):
            self.stats['cache_hits'] += 1
            return self.weather_cache[cache_key]
        
        self.stats['cache_misses'] += 1
        
        # Simuler un appel API (en l'absence d'une vraie clé API)
        if not self.api_key:
            weather_data = await self._get_mock_weather(city)
        else:
            weather_data = await self._fetch_real_weather(city)
        
        # Mettre en cache
        self.weather_cache[cache_key] = weather_data
        self.cache_timestamps[cache_key] = time.time()
        
        self.stats['requests_made'] += 1
        self.stats['last_update'] = datetime.now().isoformat()
        
        # Ajouter à la liste des villes suivies
        if city not in [data.get('city') for data in self.weather_cache.values()]:
            self.stats['cities_tracked'] += 1
        
        return weather_data
    
    async def get_forecast(self, city: str, days: int = 5) -> Dict[str, Any]:
        """Récupère les prévisions météo"""
        cache_key = f"forecast_{city.lower()}_{days}"
        
        if self._is_cache_valid(cache_key):
            self.stats['cache_hits'] += 1
            return self.weather_cache[cache_key]
        
        self.stats['cache_misses'] += 1
        
        # Générer des prévisions simulées
        forecast_data = {
            'city': city,
            'country': 'FR',
            'forecast_days': days,
            'forecasts': []
        }
        
        base_temp = 20
        for i in range(days):
            date = datetime.now() + timedelta(days=i)
            temp_variation = (i * 2) - 5  # Variation de température
            
            forecast_data['forecasts'].append({
                'date': date.strftime('%Y-%m-%d'),
                'temperature': {
                    'min': base_temp + temp_variation - 3,
                    'max': base_temp + temp_variation + 5,
                    'unit': self.temperature_unit
                },
                'conditions': ['sunny', 'cloudy', 'rainy'][i % 3],
                'humidity': 65 + (i * 5),
                'wind_speed': 10 + (i * 2)
            })
        
        # Mettre en cache
        self.weather_cache[cache_key] = forecast_data
        self.cache_timestamps[cache_key] = time.time()
        
        self.stats['requests_made'] += 1
        
        return forecast_data
    
    async def analyze_weather_pattern(self, city: str) -> Dict[str, Any]:
        """Analyse les patterns météorologiques"""
        
        # Récupérer les données actuelles
        current_weather = await self.get_weather(city)
        forecast = await self.get_forecast(city, 7)
        
        # Analyser les tendances
        temperatures = [f['temperature']['max'] for f in forecast['forecasts']]
        avg_temp = sum(temperatures) / len(temperatures)
        temp_trend = "stable"
        
        if temperatures[-1] > temperatures[0] + 3:
            temp_trend = "increasing"
        elif temperatures[-1] < temperatures[0] - 3:
            temp_trend = "decreasing"
        
        # Conditions dominantes
        conditions = [f['conditions'] for f in forecast['forecasts']]
        dominant_condition = max(set(conditions), key=conditions.count)
        
        analysis = {
            'city': city,
            'analysis_date': datetime.now().isoformat(),
            'current_conditions': current_weather,
            'week_forecast_summary': {
                'average_temperature': round(avg_temp, 1),
                'temperature_trend': temp_trend,
                'dominant_weather': dominant_condition,
                'rainy_days': conditions.count('rainy'),
                'sunny_days': conditions.count('sunny')
            },
            'recommendations': self._generate_recommendations(current_weather, forecast),
            'alerts': self._check_weather_alerts(current_weather, forecast)
        }
        
        return analysis
    
    def _generate_recommendations(self, current: Dict, forecast: Dict) -> List[str]:
        """Génère des recommandations basées sur la météo"""
        recommendations = []
        
        # Recommandations basées sur la température
        if current['temperature']['value'] < 5:
            recommendations.append("🧥 Portez des vêtements chauds")
        elif current['temperature']['value'] > 25:
            recommendations.append("🌞 Hydratez-vous régulièrement")
        
        # Recommandations basées sur les conditions
        if current['conditions'] == 'rainy':
            recommendations.append("☔ N'oubliez pas votre parapluie")
        elif current['conditions'] == 'sunny':
            recommendations.append("😎 Parfait pour les activités extérieures")
        
        # Recommandations basées sur le vent
        if current['wind_speed'] > 20:
            recommendations.append("💨 Attention au vent fort")
        
        # Recommandations pour la semaine
        rainy_days = len([f for f in forecast['forecasts'] if f['conditions'] == 'rainy'])
        if rainy_days >= 3:
            recommendations.append("🌧️ Semaine pluvieuse prévue, planifiez en conséquence")
        
        return recommendations
    
    def _check_weather_alerts(self, current: Dict, forecast: Dict) -> List[Dict[str, str]]:
        """Vérifie s'il y a des alertes météo"""
        alerts = []
        
        # Alertes de température
        if current['temperature']['value'] < 0:
            alerts.append({
                'type': 'temperature',
                'level': 'warning',
                'message': 'Température en dessous de 0°C - Risque de gel'
            })
        elif current['temperature']['value'] > 35:
            alerts.append({
                'type': 'temperature',
                'level': 'warning',
                'message': 'Forte chaleur - Limitez les activités extérieures'
            })
        
        # Alertes de vent
        if current['wind_speed'] > 30:
            alerts.append({
                'type': 'wind',
                'level': 'warning',
                'message': 'Vent fort - Soyez prudent'
            })
        
        return alerts
    
    async def _get_mock_weather(self, city: str) -> Dict[str, Any]:
        """Génère des données météo simulées"""
        
        # Simuler une latence d'API
        await asyncio.sleep(0.1)
        
        # Données simulées basées sur la ville
        base_temp = 15
        if city.lower() in ['paris', 'lyon', 'marseille']:
            base_temp = 18
        elif city.lower() in ['nice', 'cannes', 'monaco']:
            base_temp = 22
        elif city.lower() in ['lille', 'rennes', 'brest']:
            base_temp = 12
        
        return {
            'city': city,
            'country': 'FR',
            'temperature': {
                'value': base_temp + (time.time() % 10) - 5,  # Variation
                'unit': self.temperature_unit
            },
            'conditions': ['sunny', 'cloudy', 'rainy'][int(time.time()) % 3],
            'humidity': 60 + (int(time.time()) % 30),
            'wind_speed': 5 + (int(time.time()) % 15),
            'pressure': 1013 + (int(time.time()) % 20) - 10,
            'visibility': 10,
            'uv_index': max(0, min(11, int(time.time()) % 12)),
            'last_updated': datetime.now().isoformat(),
            'source': 'mock_api'
        }
    
    async def _fetch_real_weather(self, city: str) -> Dict[str, Any]:
        """Récupère les vraies données météo (nécessite une clé API)"""
        # TODO: Implémenter l'appel à une vraie API météo
        # Pour l'instant, retourner des données simulées
        return await self._get_mock_weather(city)
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Vérifie si une entrée du cache est encore valide"""
        if cache_key not in self.cache_timestamps:
            return False
        
        age = time.time() - self.cache_timestamps[cache_key]
        return age < self.update_interval
    
    @plugin_hook('system_status_check')
    async def on_system_status_check(self):
        """Hook appelé lors des vérifications de statut système"""
        logger.info(f"Weather Agent status check - Tracking {self.stats['cities_tracked']} cities")
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Retourne les métriques du plugin"""
        return {
            'plugin_metrics': self.stats,
            'cache_size': len(self.weather_cache),
            'cached_cities': list(set([data.get('city') for data in self.weather_cache.values()])),
            'cache_hit_rate': (self.stats['cache_hits'] / max(1, self.stats['cache_hits'] + self.stats['cache_misses'])) * 100
        }
    
    async def validate_config(self, config: Dict[str, Any]) -> bool:
        """Valide la configuration du plugin"""
        required_fields = ['default_city', 'update_interval', 'temperature_unit']
        
        for field in required_fields:
            if field not in config:
                logger.error(f"Missing required config field: {field}")
                return False
        
        if config['temperature_unit'] not in ['celsius', 'fahrenheit', 'kelvin']:
            logger.error(f"Invalid temperature unit: {config['temperature_unit']}")
            return False
        
        if config['update_interval'] < 60:
            logger.warning("Update interval too short, minimum 60 seconds recommended")
        
        return True

# Point d'entrée du plugin
def create_plugin(config: Dict[str, Any] = None) -> WeatherAgent:
    """Factory function pour créer une instance du plugin"""
    return WeatherAgent(config)

# Export pour compatibilité
WeatherAgentPlugin = WeatherAgent