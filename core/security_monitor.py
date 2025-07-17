"""
Master Plan IA 2025 - Security Monitoring System
Système de monitoring de sécurité en temps réel avec alertes
"""

import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import re

logger = logging.getLogger(__name__)


class ThreatLevel(Enum):
    """Niveaux de menace"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SecurityEventType(Enum):
    """Types d'événements de sécurité"""
    # Authentification
    LOGIN_ATTEMPT = "login_attempt"
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    BRUTE_FORCE_DETECTED = "brute_force_detected"
    
    # Autorisation
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    ADMIN_ACTION = "admin_action"
    
    # Validation
    INVALID_INPUT = "invalid_input"
    SQL_INJECTION_ATTEMPT = "sql_injection_attempt"
    XSS_ATTEMPT = "xss_attempt"
    PATH_TRAVERSAL_ATTEMPT = "path_traversal_attempt"
    
    # Rate limiting
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    DDOS_PATTERN_DETECTED = "ddos_pattern_detected"
    
    # Système
    SECURITY_CONFIG_CHANGED = "security_config_changed"
    SUSPICIOUS_PATTERN = "suspicious_pattern"
    ANOMALY_DETECTED = "anomaly_detected"


@dataclass
class SecurityEvent:
    """Événement de sécurité"""
    event_type: SecurityEventType
    timestamp: float
    source_ip: str
    user_id: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    threat_level: ThreatLevel = ThreatLevel.LOW
    handled: bool = False


@dataclass
class SecurityAlert:
    """Alerte de sécurité"""
    alert_id: str
    threat_level: ThreatLevel
    title: str
    description: str
    events: List[SecurityEvent]
    created_at: datetime
    actions_taken: List[str] = field(default_factory=list)
    resolved: bool = False


class SecurityMonitor:
    """Moniteur de sécurité avancé avec détection d'anomalies"""
    
    def __init__(self):
        # Configuration
        self.config = {
            # Seuils de détection
            'login_failure_threshold': 5,  # Échecs avant alerte
            'login_failure_window': 300,    # Fenêtre de 5 minutes
            'rate_limit_threshold': 100,    # Requêtes par minute
            'suspicious_pattern_threshold': 10,  # Patterns suspects
            
            # Blocage automatique
            'auto_block_enabled': True,
            'block_duration': 3600,  # 1 heure
            'permanent_block_threshold': 3,  # Blocages avant ban permanent
        }
        
        # État du système
        self.events: deque = deque(maxlen=10000)  # Événements récents
        self.alerts: Dict[str, SecurityAlert] = {}
        self.blocked_ips: Dict[str, float] = {}  # IP -> timestamp de fin de blocage
        self.suspicious_ips: Dict[str, int] = defaultdict(int)
        self.user_activity: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        
        # Patterns de détection
        self.compile_patterns()
        
        # Statistiques
        self.stats = defaultdict(int)
        
        # Background tasks
        self.monitoring_task = None
        self.is_running = False
        
        logger.info("🛡️ Security Monitor initialized")
    
    def compile_patterns(self):
        """Compile les patterns de détection"""
        self.sql_patterns = [
            re.compile(r'(union|select|insert|update|delete|drop|create|alter)\s+', re.IGNORECASE),
            re.compile(r'(--|#|/\*|\*/)', re.IGNORECASE),
            re.compile(r'(\bor\b|\band\b)\s+\d+\s*=\s*\d+', re.IGNORECASE),
        ]
        
        self.xss_patterns = [
            re.compile(r'<script[^>]*>.*?</script>', re.IGNORECASE),
            re.compile(r'javascript:', re.IGNORECASE),
            re.compile(r'on\w+\s*=', re.IGNORECASE),
            re.compile(r'<iframe[^>]*>', re.IGNORECASE),
        ]
        
        self.path_traversal_patterns = [
            re.compile(r'(\.\./|\.\.\\|%2e%2e%2f|%2e%2e%5c)'),
            re.compile(r'(etc/passwd|windows/system32)'),
        ]
        
        self.command_injection_patterns = [
            re.compile(r'[;&|`$\(\){}[\]]'),
            re.compile(r'(exec|eval|system|shell_exec)'),
        ]
    
    async def start(self):
        """Démarre le monitoring de sécurité"""
        if self.is_running:
            return
        
        self.is_running = True
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("✅ Security monitoring started")
    
    async def stop(self):
        """Arrête le monitoring"""
        self.is_running = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 Security monitoring stopped")
    
    async def log_event(self, event: SecurityEvent):
        """Enregistre un événement de sécurité"""
        # Ajouter à la queue
        self.events.append(event)
        
        # Mettre à jour les stats
        self.stats[event.event_type.value] += 1
        self.stats['total_events'] += 1
        
        # Tracer l'activité par IP
        if event.source_ip:
            self.user_activity[event.source_ip].append(event)
        
        # Vérifier si l'IP est bloquée
        if event.source_ip in self.blocked_ips:
            event.handled = True
            return
        
        # Analyser l'événement
        await self._analyze_event(event)
        
        # Logger selon le niveau
        if event.threat_level in [ThreatLevel.HIGH, ThreatLevel.CRITICAL]:
            logger.error(f"🚨 Security event: {event.event_type.value} from {event.source_ip}")
        elif event.threat_level == ThreatLevel.MEDIUM:
            logger.warning(f"⚠️ Security event: {event.event_type.value} from {event.source_ip}")
        else:
            logger.info(f"Security event: {event.event_type.value} from {event.source_ip}")
    
    async def _analyze_event(self, event: SecurityEvent):
        """Analyse un événement pour détecter les menaces"""
        
        # Détection de brute force
        if event.event_type == SecurityEventType.LOGIN_FAILURE:
            await self._check_brute_force(event)
        
        # Détection d'injection
        elif event.event_type in [
            SecurityEventType.SQL_INJECTION_ATTEMPT,
            SecurityEventType.XSS_ATTEMPT,
            SecurityEventType.PATH_TRAVERSAL_ATTEMPT
        ]:
            await self._handle_injection_attempt(event)
        
        # Rate limiting
        elif event.event_type == SecurityEventType.RATE_LIMIT_EXCEEDED:
            await self._handle_rate_limit_violation(event)
        
        # Escalade de privilèges
        elif event.event_type == SecurityEventType.PRIVILEGE_ESCALATION:
            await self._handle_privilege_escalation(event)
    
    async def _check_brute_force(self, event: SecurityEvent):
        """Vérifie les tentatives de brute force"""
        ip = event.source_ip
        window = self.config['login_failure_window']
        threshold = self.config['login_failure_threshold']
        
        # Compter les échecs récents
        recent_failures = [
            e for e in self.user_activity[ip]
            if e.event_type == SecurityEventType.LOGIN_FAILURE
            and e.timestamp > time.time() - window
        ]
        
        if len(recent_failures) >= threshold:
            # Créer une alerte
            alert = SecurityAlert(
                alert_id=f"brute_force_{ip}_{int(time.time())}",
                threat_level=ThreatLevel.HIGH,
                title=f"Brute force attack detected from {ip}",
                description=f"{len(recent_failures)} failed login attempts in {window} seconds",
                events=recent_failures,
                created_at=datetime.now()
            )
            
            self.alerts[alert.alert_id] = alert
            
            # Bloquer l'IP si auto-block activé
            if self.config['auto_block_enabled']:
                await self.block_ip(ip, self.config['block_duration'])
                alert.actions_taken.append(f"Blocked IP {ip} for {self.config['block_duration']} seconds")
            
            # Logger un nouvel événement
            await self.log_event(SecurityEvent(
                event_type=SecurityEventType.BRUTE_FORCE_DETECTED,
                timestamp=time.time(),
                source_ip=ip,
                threat_level=ThreatLevel.HIGH,
                details={'failed_attempts': len(recent_failures)}
            ))
    
    async def _handle_injection_attempt(self, event: SecurityEvent):
        """Gère les tentatives d'injection"""
        ip = event.source_ip
        
        # Incrémenter le compteur de suspicion
        self.suspicious_ips[ip] += 1
        
        # Si trop de tentatives, bloquer
        if self.suspicious_ips[ip] >= self.config['suspicious_pattern_threshold']:
            await self.block_ip(ip, self.config['block_duration'] * 2)  # Blocage plus long
            
            # Créer une alerte critique
            alert = SecurityAlert(
                alert_id=f"injection_{ip}_{int(time.time())}",
                threat_level=ThreatLevel.CRITICAL,
                title=f"Multiple injection attempts from {ip}",
                description=f"Detected {self.suspicious_ips[ip]} injection attempts",
                events=[event],
                created_at=datetime.now()
            )
            
            alert.actions_taken.append(f"Blocked IP {ip} for extended duration")
            self.alerts[alert.alert_id] = alert
    
    async def _handle_rate_limit_violation(self, event: SecurityEvent):
        """Gère les violations de rate limit"""
        ip = event.source_ip
        
        # Vérifier le pattern DDoS
        recent_violations = [
            e for e in self.user_activity[ip]
            if e.event_type == SecurityEventType.RATE_LIMIT_EXCEEDED
            and e.timestamp > time.time() - 300  # 5 minutes
        ]
        
        if len(recent_violations) > 5:
            # Pattern DDoS détecté
            await self.log_event(SecurityEvent(
                event_type=SecurityEventType.DDOS_PATTERN_DETECTED,
                timestamp=time.time(),
                source_ip=ip,
                threat_level=ThreatLevel.CRITICAL,
                details={'violations': len(recent_violations)}
            ))
            
            # Blocage immédiat
            await self.block_ip(ip, self.config['block_duration'] * 4)
    
    async def _handle_privilege_escalation(self, event: SecurityEvent):
        """Gère les tentatives d'escalade de privilèges"""
        # Alerte critique immédiate
        alert = SecurityAlert(
            alert_id=f"privilege_escalation_{int(time.time())}",
            threat_level=ThreatLevel.CRITICAL,
            title="Privilege escalation attempt detected",
            description=f"User {event.user_id} attempted privilege escalation",
            events=[event],
            created_at=datetime.now()
        )
        
        self.alerts[alert.alert_id] = alert
        
        # Actions supplémentaires selon la configuration
        if event.user_id:
            # Potentiellement révoquer les tokens de l'utilisateur
            alert.actions_taken.append(f"Flagged user {event.user_id} for review")
    
    async def block_ip(self, ip: str, duration: int):
        """Bloque une adresse IP"""
        self.blocked_ips[ip] = time.time() + duration
        logger.warning(f"🚫 Blocked IP {ip} for {duration} seconds")
        
        # Vérifier si c'est un blocage permanent
        block_count = self.stats.get(f'blocks_{ip}', 0) + 1
        self.stats[f'blocks_{ip}'] = block_count
        
        if block_count >= self.config['permanent_block_threshold']:
            # Blocage permanent
            self.blocked_ips[ip] = float('inf')
            logger.error(f"⛔ Permanently blocked IP {ip} after {block_count} violations")
    
    def is_ip_blocked(self, ip: str) -> bool:
        """Vérifie si une IP est bloquée"""
        if ip not in self.blocked_ips:
            return False
        
        # Vérifier si le blocage a expiré
        if self.blocked_ips[ip] != float('inf') and time.time() > self.blocked_ips[ip]:
            del self.blocked_ips[ip]
            return False
        
        return True
    
    def detect_patterns(self, input_str: str) -> List[SecurityEventType]:
        """Détecte les patterns malveillants dans une chaîne"""
        detected = []
        
        # SQL Injection
        for pattern in self.sql_patterns:
            if pattern.search(input_str):
                detected.append(SecurityEventType.SQL_INJECTION_ATTEMPT)
                break
        
        # XSS
        for pattern in self.xss_patterns:
            if pattern.search(input_str):
                detected.append(SecurityEventType.XSS_ATTEMPT)
                break
        
        # Path Traversal
        for pattern in self.path_traversal_patterns:
            if pattern.search(input_str):
                detected.append(SecurityEventType.PATH_TRAVERSAL_ATTEMPT)
                break
        
        return detected
    
    async def _monitoring_loop(self):
        """Boucle de monitoring principale"""
        while self.is_running:
            try:
                # Nettoyer les blocages expirés
                current_time = time.time()
                expired_blocks = [
                    ip for ip, expiry in self.blocked_ips.items()
                    if expiry != float('inf') and current_time > expiry
                ]
                
                for ip in expired_blocks:
                    del self.blocked_ips[ip]
                    logger.info(f"✅ Unblocked IP {ip}")
                
                # Analyser les patterns globaux
                await self._analyze_global_patterns()
                
                # Mettre à jour les métriques
                self.stats['blocked_ips'] = len(self.blocked_ips)
                self.stats['active_alerts'] = len([a for a in self.alerts.values() if not a.resolved])
                
                await asyncio.sleep(30)  # Vérifier toutes les 30 secondes
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(60)
    
    async def _analyze_global_patterns(self):
        """Analyse les patterns globaux pour détecter les anomalies"""
        # Analyser les événements des 5 dernières minutes
        recent_events = [
            e for e in self.events
            if e.timestamp > time.time() - 300
        ]
        
        if not recent_events:
            return
        
        # Détecter les anomalies par type d'événement
        event_counts = defaultdict(int)
        for event in recent_events:
            event_counts[event.event_type] += 1
        
        # Alerter si un type d'événement est anormalement élevé
        for event_type, count in event_counts.items():
            normal_rate = self.stats.get(f'avg_{event_type.value}', 10)
            
            if count > normal_rate * 3:  # 3x le taux normal
                await self.log_event(SecurityEvent(
                    event_type=SecurityEventType.ANOMALY_DETECTED,
                    timestamp=time.time(),
                    source_ip="system",
                    threat_level=ThreatLevel.MEDIUM,
                    details={
                        'anomaly_type': event_type.value,
                        'count': count,
                        'normal_rate': normal_rate
                    }
                ))
    
    def get_security_status(self) -> Dict[str, Any]:
        """Retourne le statut de sécurité actuel"""
        return {
            'is_running': self.is_running,
            'total_events': self.stats['total_events'],
            'blocked_ips': len(self.blocked_ips),
            'active_alerts': len([a for a in self.alerts.values() if not a.resolved]),
            'threat_level': self._calculate_threat_level(),
            'event_distribution': {
                event_type.value: self.stats.get(event_type.value, 0)
                for event_type in SecurityEventType
            },
            'recent_alerts': [
                {
                    'alert_id': alert.alert_id,
                    'threat_level': alert.threat_level.value,
                    'title': alert.title,
                    'created_at': alert.created_at.isoformat()
                }
                for alert in sorted(
                    self.alerts.values(),
                    key=lambda a: a.created_at,
                    reverse=True
                )[:5]
            ]
        }
    
    def _calculate_threat_level(self) -> str:
        """Calcule le niveau de menace global"""
        # Basé sur les alertes actives
        active_alerts = [a for a in self.alerts.values() if not a.resolved]
        
        if any(a.threat_level == ThreatLevel.CRITICAL for a in active_alerts):
            return ThreatLevel.CRITICAL.value
        elif any(a.threat_level == ThreatLevel.HIGH for a in active_alerts):
            return ThreatLevel.HIGH.value
        elif any(a.threat_level == ThreatLevel.MEDIUM for a in active_alerts):
            return ThreatLevel.MEDIUM.value
        elif len(self.blocked_ips) > 10:
            return ThreatLevel.MEDIUM.value
        else:
            return ThreatLevel.LOW.value
    
    def resolve_alert(self, alert_id: str, resolution: str):
        """Résout une alerte"""
        if alert_id in self.alerts:
            self.alerts[alert_id].resolved = True
            self.alerts[alert_id].actions_taken.append(f"Resolved: {resolution}")
            logger.info(f"✅ Alert {alert_id} resolved")


# Instance globale
security_monitor = SecurityMonitor()


# Middleware FastAPI pour intégration
class SecurityMonitoringMiddleware:
    """Middleware pour intégrer le monitoring de sécurité"""
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            # Extraire les informations de la requête
            path = scope["path"]
            method = scope["method"]
            headers = dict(scope["headers"])
            
            # Obtenir l'IP cliente
            client_ip = None
            if b"x-forwarded-for" in headers:
                client_ip = headers[b"x-forwarded-for"].decode().split(",")[0].strip()
            elif scope.get("client"):
                client_ip = scope["client"][0]
            
            # Vérifier si l'IP est bloquée
            if client_ip and security_monitor.is_ip_blocked(client_ip):
                response = {
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [(b"content-type", b"application/json")],
                }
                await send(response)
                
                body = json.dumps({"error": "Access denied"}).encode()
                await send({
                    "type": "http.response.body",
                    "body": body,
                })
                return
            
            # Continuer avec la requête
            await self.app(scope, receive, send)


if __name__ == "__main__":
    # Test du système
    async def test_security_monitor():
        await security_monitor.start()
        
        # Simuler quelques événements
        test_events = [
            SecurityEvent(
                event_type=SecurityEventType.LOGIN_FAILURE,
                timestamp=time.time(),
                source_ip="192.168.1.100",
                threat_level=ThreatLevel.LOW
            ),
            SecurityEvent(
                event_type=SecurityEventType.SQL_INJECTION_ATTEMPT,
                timestamp=time.time(),
                source_ip="10.0.0.50",
                threat_level=ThreatLevel.HIGH,
                details={"input": "'; DROP TABLE users; --"}
            ),
            SecurityEvent(
                event_type=SecurityEventType.RATE_LIMIT_EXCEEDED,
                timestamp=time.time(),
                source_ip="172.16.0.10",
                threat_level=ThreatLevel.MEDIUM
            )
        ]
        
        for event in test_events:
            await security_monitor.log_event(event)
        
        # Afficher le statut
        print(json.dumps(security_monitor.get_security_status(), indent=2))
        
        await security_monitor.stop()
    
    asyncio.run(test_security_monitor())