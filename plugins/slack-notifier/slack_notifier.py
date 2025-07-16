#!/usr/bin/env python3
"""
Plugin Slack Notifier - Notifications Slack intelligentes
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import deque
import logging

# Import du système de plugins
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'core'))

from plugin_system import PluginInterface, plugin_hook, requires_permission

logger = logging.getLogger(__name__)

class SlackNotifier(PluginInterface):
    """Plugin de notification Slack intelligent"""
    
    PLUGIN_NAME = "slack-notifier"
    PLUGIN_VERSION = "1.0.0"
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.webhook_url = config.get('webhook_url', '')
        self.default_channel = config.get('default_channel', '#general')
        self.username = config.get('username', 'Master Plan IA')
        self.icon_emoji = config.get('icon_emoji', ':robot_face:')
        self.alert_levels = config.get('alert_levels', ['error', 'warning', 'info'])
        self.rate_limit = config.get('rate_limit', 10)  # messages par minute
        
        # Rate limiting
        self.message_timestamps = deque()
        
        # Templates de messages
        self.message_templates = {
            'system_start': {
                'color': 'good',
                'emoji': ':white_check_mark:',
                'title': 'Système démarré'
            },
            'system_stop': {
                'color': 'warning',
                'emoji': ':octagonal_sign:',
                'title': 'Système arrêté'
            },
            'agent_error': {
                'color': 'danger',
                'emoji': ':x:',
                'title': 'Erreur agent'
            },
            'task_completed': {
                'color': 'good',
                'emoji': ':heavy_check_mark:',
                'title': 'Tâche terminée'
            },
            'workflow_failed': {
                'color': 'danger',
                'emoji': ':broken_heart:',
                'title': 'Workflow échoué'
            },
            'performance_alert': {
                'color': 'warning',
                'emoji': ':warning:',
                'title': 'Alerte performance'
            },
            'plugin_loaded': {
                'color': 'good',
                'emoji': ':electric_plug:',
                'title': 'Plugin chargé'
            },
            'cache_stats': {
                'color': '#36a64f',
                'emoji': ':bar_chart:',
                'title': 'Statistiques cache'
            }
        }
        
        # Statistiques
        self.stats = {
            'messages_sent': 0,
            'messages_failed': 0,
            'rate_limited': 0,
            'last_notification': None,
            'channels_used': set(),
            'alert_types_sent': {}
        }
    
    async def initialize(self) -> bool:
        """Initialise le notificateur Slack"""
        try:
            logger.info(f"💬 Initializing Slack Notifier...")
            
            # Valider la configuration
            if not self.webhook_url:
                logger.error("❌ No webhook URL provided")
                return False
            
            # Test de connectivité
            test_result = await self.send_notification(
                message="🚀 Master Plan IA - Slack Notifier initialisé",
                level="info",
                channel=self.default_channel
            )
            
            if not test_result:
                logger.warning("⚠️ Failed to send test message, but continuing...")
            
            self.is_initialized = True
            logger.info(f"✅ Slack Notifier initialized")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Slack Notifier: {e}")
            return False
    
    async def shutdown(self) -> bool:
        """Arrête le notificateur proprement"""
        logger.info("🛑 Shutting down Slack Notifier...")
        
        # Envoyer une notification d'arrêt
        await self.send_notification(
            message="🛑 Master Plan IA - Système arrêté",
            level="warning",
            channel=self.default_channel
        )
        
        return True
    
    @requires_permission('api_calls')
    async def send_notification(self, 
                              message: str,
                              level: str = "info",
                              channel: Optional[str] = None,
                              title: Optional[str] = None,
                              fields: Optional[List[Dict[str, str]]] = None,
                              template: Optional[str] = None) -> bool:
        """Envoie une notification Slack"""
        
        # Vérifier le rate limiting
        if not self._check_rate_limit():
            self.stats['rate_limited'] += 1
            logger.warning("⚠️ Rate limit exceeded, notification skipped")
            return False
        
        # Vérifier si le niveau d'alerte est activé
        if level not in self.alert_levels:
            return True  # Silencieusement ignoré
        
        try:
            # Construire le payload
            payload = await self._build_payload(
                message, level, channel, title, fields, template
            )
            
            # Simuler l'envoi (sans vraie URL de webhook)
            if self.webhook_url.startswith('https://hooks.slack.com'):
                # TODO: Implémenter l'envoi réel avec requests
                success = await self._send_real_message(payload)
            else:
                # Mode simulation
                success = await self._simulate_send(payload)
            
            if success:
                self.stats['messages_sent'] += 1
                self.stats['last_notification'] = datetime.now().isoformat()
                self.stats['channels_used'].add(channel or self.default_channel)
                
                # Compter par type d'alerte
                if level not in self.stats['alert_types_sent']:
                    self.stats['alert_types_sent'][level] = 0
                self.stats['alert_types_sent'][level] += 1
                
                logger.debug(f"📤 Slack notification sent: {level} - {message[:50]}...")
                return True
            else:
                self.stats['messages_failed'] += 1
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to send Slack notification: {e}")
            self.stats['messages_failed'] += 1
            return False
    
    async def _build_payload(self,
                           message: str,
                           level: str,
                           channel: Optional[str],
                           title: Optional[str],
                           fields: Optional[List[Dict[str, str]]],
                           template: Optional[str]) -> Dict[str, Any]:
        """Construit le payload pour Slack"""
        
        # Template ou configuration par défaut
        if template and template in self.message_templates:
            tmpl = self.message_templates[template]
            color = tmpl['color']
            emoji = tmpl['emoji']
            title = title or tmpl['title']
        else:
            # Couleurs par niveau
            color_map = {
                'error': 'danger',
                'warning': 'warning',
                'info': 'good',
                'success': 'good'
            }
            color = color_map.get(level, '#36a64f')
            
            # Emojis par niveau
            emoji_map = {
                'error': ':x:',
                'warning': ':warning:',
                'info': ':information_source:',
                'success': ':white_check_mark:'
            }
            emoji = emoji_map.get(level, ':robot_face:')
        
        # Construire l'attachment
        attachment = {
            'color': color,
            'title': f"{emoji} {title or level.upper()}",
            'text': message,
            'timestamp': int(time.time()),
            'footer': 'Master Plan IA',
            'footer_icon': 'https://via.placeholder.com/16x16.png'
        }
        
        # Ajouter des champs si fournis
        if fields:
            attachment['fields'] = fields
        
        # Payload principal
        payload = {
            'channel': channel or self.default_channel,
            'username': self.username,
            'icon_emoji': self.icon_emoji,
            'attachments': [attachment]
        }
        
        return payload
    
    async def _send_real_message(self, payload: Dict[str, Any]) -> bool:
        """Envoie un vrai message Slack (nécessite requests)"""
        # TODO: Implémenter avec requests
        # import requests
        # response = requests.post(self.webhook_url, json=payload)
        # return response.status_code == 200
        
        # Pour l'instant, simuler
        return await self._simulate_send(payload)
    
    async def _simulate_send(self, payload: Dict[str, Any]) -> bool:
        """Simule l'envoi d'un message Slack"""
        await asyncio.sleep(0.1)  # Simuler la latence réseau
        
        logger.info(f"📱 [SIMULATION] Slack message to {payload['channel']}:")
        logger.info(f"   Title: {payload['attachments'][0]['title']}")
        logger.info(f"   Message: {payload['attachments'][0]['text']}")
        
        # Simuler 95% de réussite
        return time.time() % 20 != 0
    
    def _check_rate_limit(self) -> bool:
        """Vérifie le rate limiting"""
        now = time.time()
        
        # Nettoyer les anciens timestamps
        while self.message_timestamps and self.message_timestamps[0] < now - 60:
            self.message_timestamps.popleft()
        
        # Vérifier la limite
        if len(self.message_timestamps) >= self.rate_limit:
            return False
        
        # Ajouter le timestamp actuel
        self.message_timestamps.append(now)
        return True
    
    # Hooks pour les événements système
    
    @plugin_hook('system_started')
    async def on_system_started(self):
        """Hook appelé au démarrage du système"""
        await self.send_notification(
            message="Le système Master Plan IA a démarré avec succès",
            level="success",
            template="system_start",
            fields=[
                {
                    'title': 'Timestamp',
                    'value': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'short': True
                }
            ]
        )
    
    @plugin_hook('system_stopping')
    async def on_system_stopping(self):
        """Hook appelé à l'arrêt du système"""
        await self.send_notification(
            message="Le système Master Plan IA s'arrête",
            level="warning",
            template="system_stop"
        )
    
    @plugin_hook('plugin_loaded')
    async def on_plugin_loaded(self, plugin_name: str, plugin_instance: Any):
        """Hook appelé quand un plugin est chargé"""
        await self.send_notification(
            message=f"Plugin '{plugin_name}' chargé avec succès",
            level="info",
            template="plugin_loaded",
            fields=[
                {
                    'title': 'Plugin',
                    'value': plugin_name,
                    'short': True
                },
                {
                    'title': 'Type',
                    'value': getattr(plugin_instance, 'PLUGIN_VERSION', 'Unknown'),
                    'short': True
                }
            ]
        )
    
    @plugin_hook('agent_error')
    async def on_agent_error(self, agent_id: str, error_message: str):
        """Hook appelé en cas d'erreur d'agent"""
        await self.send_notification(
            message=f"Erreur dans l'agent {agent_id}: {error_message}",
            level="error",
            template="agent_error",
            fields=[
                {
                    'title': 'Agent ID',
                    'value': agent_id,
                    'short': True
                },
                {
                    'title': 'Erreur',
                    'value': error_message[:100] + ('...' if len(error_message) > 100 else ''),
                    'short': False
                }
            ]
        )
    
    @plugin_hook('task_completed')
    async def on_task_completed(self, task_id: str, result: Dict[str, Any]):
        """Hook appelé quand une tâche est terminée"""
        success = result.get('success', False)
        duration = result.get('duration', 0)
        
        if success:
            await self.send_notification(
                message=f"Tâche {task_id} terminée avec succès en {duration:.2f}s",
                level="success",
                template="task_completed",
                fields=[
                    {
                        'title': 'Task ID',
                        'value': task_id,
                        'short': True
                    },
                    {
                        'title': 'Durée',
                        'value': f"{duration:.2f}s",
                        'short': True
                    }
                ]
            )
    
    @plugin_hook('performance_alert')
    async def on_performance_alert(self, alert_type: str, details: Dict[str, Any]):
        """Hook appelé pour les alertes de performance"""
        await self.send_notification(
            message=f"Alerte performance: {alert_type}",
            level="warning",
            template="performance_alert",
            fields=[
                {
                    'title': 'Type d\'alerte',
                    'value': alert_type,
                    'short': True
                },
                {
                    'title': 'Valeur',
                    'value': str(details.get('value', 'N/A')),
                    'short': True
                },
                {
                    'title': 'Seuil',
                    'value': str(details.get('threshold', 'N/A')),
                    'short': True
                }
            ]
        )
    
    async def send_daily_report(self) -> bool:
        """Envoie un rapport journalier"""
        # Collecter les statistiques système
        report_fields = [
            {
                'title': 'Messages envoyés',
                'value': str(self.stats['messages_sent']),
                'short': True
            },
            {
                'title': 'Échecs',
                'value': str(self.stats['messages_failed']),
                'short': True
            },
            {
                'title': 'Canaux utilisés',
                'value': str(len(self.stats['channels_used'])),
                'short': True
            },
            {
                'title': 'Types d\'alertes',
                'value': ', '.join(self.stats['alert_types_sent'].keys()),
                'short': False
            }
        ]
        
        return await self.send_notification(
            message="Rapport journalier des notifications Slack",
            level="info",
            title="📊 Rapport journalier",
            fields=report_fields
        )
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Retourne les métriques du plugin"""
        return {
            'plugin_metrics': {
                **self.stats,
                'channels_used': list(self.stats['channels_used'])  # Convertir set en list
            },
            'config': {
                'rate_limit': self.rate_limit,
                'alert_levels': self.alert_levels,
                'default_channel': self.default_channel
            },
            'rate_limiting': {
                'current_window_messages': len(self.message_timestamps),
                'limit': self.rate_limit,
                'window_size_seconds': 60
            }
        }
    
    async def validate_config(self, config: Dict[str, Any]) -> bool:
        """Valide la configuration du plugin"""
        if 'webhook_url' not in config:
            logger.error("Missing webhook_url in config")
            return False
        
        if 'rate_limit' in config and config['rate_limit'] < 1:
            logger.error("Rate limit must be at least 1")
            return False
        
        if 'alert_levels' in config:
            valid_levels = ['error', 'warning', 'info', 'success']
            for level in config['alert_levels']:
                if level not in valid_levels:
                    logger.error(f"Invalid alert level: {level}")
                    return False
        
        return True

# Point d'entrée du plugin
def create_plugin(config: Dict[str, Any] = None) -> SlackNotifier:
    """Factory function pour créer une instance du plugin"""
    return SlackNotifier(config)

# Export pour compatibilité
SlackNotifierPlugin = SlackNotifier