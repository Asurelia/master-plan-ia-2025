// Master Plan IA 2025 - Dashboard JavaScript

class DashboardManager {
    constructor() {
        this.websocket = null;
        this.currentSection = 'overview';
        this.charts = {};
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;
        this.lastUpdate = null;
        this.isConnected = false;
        
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.setupWebSocket();
        this.setupCharts();
        this.loadInitialData();
        this.startUpdateTimer();
    }
    
    setupEventListeners() {
        // Navigation
        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const section = e.target.getAttribute('href').substring(1);
                this.showSection(section);
            });
        });
        
        // Window resize
        window.addEventListener('resize', () => {
            this.resizeCharts();
        });
        
        // Visibility change
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                this.pauseUpdates();
            } else {
                this.resumeUpdates();
            }
        });
    }
    
    setupWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        
        try {
            this.websocket = new WebSocket(wsUrl);
            
            this.websocket.onopen = () => {
                console.log('WebSocket connected');
                this.isConnected = true;
                this.reconnectAttempts = 0;
                this.updateConnectionStatus('connected');
            };
            
            this.websocket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleWebSocketMessage(data);
                } catch (error) {
                    console.error('Error parsing WebSocket message:', error);
                }
            };
            
            this.websocket.onclose = () => {
                console.log('WebSocket disconnected');
                this.isConnected = false;
                this.updateConnectionStatus('disconnected');
                this.attemptReconnect();
            };
            
            this.websocket.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.updateConnectionStatus('error');
            };
            
        } catch (error) {
            console.error('Failed to setup WebSocket:', error);
            this.updateConnectionStatus('error');
        }
    }
    
    handleWebSocketMessage(data) {
        this.lastUpdate = new Date();
        this.updateLastUpdateTime();
        
        switch (data.type) {
            case 'metrics_update':
                this.updateMetrics(data.data);
                break;
            case 'action_completed':
                this.showActionResult(data.data);
                break;
            case 'strategy_updated':
                this.updateStrategy(data.data);
                break;
            case 'alert':
                this.showAlert(data.data);
                break;
            default:
                console.log('Unknown message type:', data.type);
        }
    }
    
    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            this.updateConnectionStatus('reconnecting');
            
            setTimeout(() => {
                console.log(`Attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
                this.setupWebSocket();
            }, this.reconnectDelay * this.reconnectAttempts);
        } else {
            console.log('Max reconnect attempts reached');
            this.updateConnectionStatus('failed');
        }
    }
    
    updateConnectionStatus(status) {
        const statusElement = document.getElementById('connection-status');
        const textElement = document.getElementById('connection-text');
        
        if (!statusElement || !textElement) return;
        
        statusElement.className = 'fas fa-circle';
        
        switch (status) {
            case 'connected':
                statusElement.classList.add('text-success');
                textElement.textContent = 'Connecté';
                break;
            case 'disconnected':
                statusElement.classList.add('text-danger');
                textElement.textContent = 'Déconnecté';
                break;
            case 'reconnecting':
                statusElement.classList.add('text-warning');
                textElement.textContent = 'Reconnexion...';
                break;
            case 'error':
            case 'failed':
                statusElement.classList.add('text-danger');
                textElement.textContent = 'Erreur';
                break;
        }
    }
    
    updateLastUpdateTime() {
        const element = document.getElementById('last-update');
        if (element && this.lastUpdate) {
            element.textContent = this.lastUpdate.toLocaleTimeString();
        }
    }
    
    showSection(sectionName) {
        // Masquer toutes les sections
        document.querySelectorAll('.dashboard-section').forEach(section => {
            section.style.display = 'none';
        });
        
        // Afficher la section demandée
        const targetSection = document.getElementById(sectionName);
        if (targetSection) {
            targetSection.style.display = 'block';
            this.currentSection = sectionName;
        }
        
        // Mettre à jour la navigation
        document.querySelectorAll('.nav-link').forEach(link => {
            link.classList.remove('active');
        });
        
        const activeLink = document.querySelector(`[href="#${sectionName}"]`);
        if (activeLink) {
            activeLink.classList.add('active');
        }
        
        // Charger les données spécifiques à la section
        this.loadSectionData(sectionName);
    }
    
    setupCharts() {
        // Graphique de performance
        const performanceCtx = document.getElementById('performanceChart');
        if (performanceCtx) {
            this.charts.performance = new Chart(performanceCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Temps de réponse (ms)',
                        data: [],
                        borderColor: 'rgb(75, 192, 192)',
                        backgroundColor: 'rgba(75, 192, 192, 0.1)',
                        tension: 0.1
                    }, {
                        label: 'Taux de succès (%)',
                        data: [],
                        borderColor: 'rgb(255, 99, 132)',
                        backgroundColor: 'rgba(255, 99, 132, 0.1)',
                        tension: 0.1,
                        yAxisID: 'y1'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            type: 'linear',
                            display: true,
                            position: 'left',
                            title: {
                                display: true,
                                text: 'Temps (ms)'
                            }
                        },
                        y1: {
                            type: 'linear',
                            display: true,
                            position: 'right',
                            title: {
                                display: true,
                                text: 'Taux (%)'
                            },
                            grid: {
                                drawOnChartArea: false
                            }
                        }
                    },
                    plugins: {
                        title: {
                            display: true,
                            text: 'Performance en temps réel'
                        }
                    }
                }
            });
        }
        
        // Graphique de distribution des tâches
        const taskDistCtx = document.getElementById('taskDistributionChart');
        if (taskDistCtx) {
            this.charts.taskDistribution = new Chart(taskDistCtx, {
                type: 'pie',
                data: {
                    labels: ['Analyse', 'Génération', 'Traduction', 'Autres'],
                    datasets: [{
                        data: [30, 25, 20, 25],
                        backgroundColor: [
                            '#FF6384',
                            '#36A2EB',
                            '#FFCE56',
                            '#4BC0C0'
                        ]
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        title: {
                            display: true,
                            text: 'Répartition des tâches'
                        }
                    }
                }
            });
        }
    }
    
    async loadInitialData() {
        try {
            // Charger les données initiales
            await Promise.all([
                this.loadMetrics(),
                this.loadAgents(),
                this.loadWorkflows(),
                this.loadAlerts()
            ]);
        } catch (error) {
            console.error('Error loading initial data:', error);
        }
    }
    
    async loadMetrics() {
        try {
            const response = await fetch('/api/metrics');
            const data = await response.json();
            this.updateMetrics(data);
        } catch (error) {
            console.error('Error loading metrics:', error);
        }
    }
    
    async loadAgents() {
        try {
            const response = await fetch('/api/agents');
            const data = await response.json();
            this.updateAgentsTable(data);
        } catch (error) {
            console.error('Error loading agents:', error);
        }
    }
    
    async loadWorkflows() {
        try {
            const response = await fetch('/api/workflows');
            const data = await response.json();
            this.updateWorkflowsTable(data);
        } catch (error) {
            console.error('Error loading workflows:', error);
        }
    }
    
    async loadAlerts() {
        try {
            const response = await fetch('/api/alerts');
            const data = await response.json();
            this.updateAlerts(data);
        } catch (error) {
            console.error('Error loading alerts:', error);
        }
    }
    
    updateMetrics(data) {
        if (!data || !data.summary) return;
        
        const summary = data.summary;
        
        // Mettre à jour les KPIs
        this.updateElement('system-health', this.getHealthText(summary.overall_health));
        this.updateElement('active-agents', data.metrics?.active_agents || 3);
        this.updateElement('active-workflows', data.metrics?.active_workflows || 0);
        this.updateElement('success-rate', `${Math.round((summary.performance_score || 0.8) * 100)}%`);
        
        // Mettre à jour les barres de progression
        this.updateProgressBar('health-progress', summary.efficiency_score || 0.8);
        this.updateProgressBar('success-progress', summary.performance_score || 0.8);
        
        // Mettre à jour les graphiques
        this.updatePerformanceChart(data);
        this.updateMetricsGrid(data.metrics);
    }
    
    updatePerformanceChart(data) {
        if (!this.charts.performance) return;
        
        const now = new Date();
        const chart = this.charts.performance;
        
        // Ajouter un nouveau point
        chart.data.labels.push(now.toLocaleTimeString());
        chart.data.datasets[0].data.push(Math.random() * 100 + 50); // Temps de réponse simulé
        chart.data.datasets[1].data.push((data.summary?.performance_score || 0.8) * 100); // Taux de succès
        
        // Limiter à 20 points
        if (chart.data.labels.length > 20) {
            chart.data.labels.shift();
            chart.data.datasets[0].data.shift();
            chart.data.datasets[1].data.shift();
        }
        
        chart.update('none');
    }
    
    updateMetricsGrid(metrics) {
        const container = document.getElementById('metrics-grid');
        if (!container || !metrics) return;
        
        container.innerHTML = '';
        
        Object.entries(metrics).forEach(([name, data]) => {
            const metricCard = this.createMetricCard(name, data);
            container.appendChild(metricCard);
        });
    }
    
    createMetricCard(name, data) {
        const card = document.createElement('div');
        card.className = 'metric-card';
        
        const value = data.latest_value || 0;
        const unit = data.definition?.unit || '';
        
        card.innerHTML = `
            <div class="metric-label">${this.formatMetricName(name)}</div>
            <div class="metric-value">${this.formatMetricValue(value)}${unit}</div>
            <div class="metric-trend trend-stable">
                <i class="fas fa-arrow-right"></i> Stable
            </div>
        `;
        
        return card;
    }
    
    updateAgentsTable(data) {
        const tbody = document.getElementById('agents-table');
        if (!tbody) return;
        
        tbody.innerHTML = '';
        
        const agents = data.agents || [];
        agents.forEach(agent => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>
                    <div class="d-flex align-items-center">
                        <span class="status-indicator ${this.getStatusClass(agent.is_healthy)}"></span>
                        <div>
                            <div class="fw-bold">${agent.name}</div>
                            <small class="text-muted">${agent.id}</small>
                        </div>
                    </div>
                </td>
                <td>
                    <span class="badge bg-secondary">${agent.type}</span>
                </td>
                <td>
                    <span class="badge ${agent.is_healthy ? 'bg-success' : 'bg-danger'}">
                        ${agent.is_healthy ? 'En ligne' : 'Hors ligne'}
                    </span>
                </td>
                <td>
                    <div class="d-flex align-items-center">
                        <div class="load-bar me-2" style="width: 60px;">
                            <div class="load-bar-fill" style="width: ${agent.load_percentage || 0}%"></div>
                        </div>
                        <span>${Math.round(agent.load_percentage || 0)}%</span>
                    </div>
                </td>
                <td>
                    <div class="d-flex align-items-center">
                        <i class="fas fa-star text-warning me-1"></i>
                        <span>4.2/5</span>
                    </div>
                </td>
                <td>
                    <button class="btn btn-sm btn-outline-primary btn-action" onclick="scaleAgent('${agent.id}', 'up')">
                        <i class="fas fa-plus"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-warning btn-action" onclick="restartAgent('${agent.id}')">
                        <i class="fas fa-redo"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger btn-action" onclick="scaleAgent('${agent.id}', 'down')">
                        <i class="fas fa-minus"></i>
                    </button>
                </td>
            `;
            tbody.appendChild(row);
        });
    }
    
    updateWorkflowsTable(data) {
        const tbody = document.getElementById('workflows-table');
        if (!tbody) return;
        
        tbody.innerHTML = '';
        
        const workflows = data.workflows || [];
        workflows.forEach(workflow => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>
                    <div class="fw-bold">${workflow.name}</div>
                    <small class="text-muted">${workflow.id}</small>
                </td>
                <td>
                    <span class="badge bg-info">${workflow.pattern}</span>
                </td>
                <td>
                    <span class="badge ${this.getStatusBadgeClass(workflow.status)}">
                        ${workflow.status}
                    </span>
                </td>
                <td>
                    <div class="d-flex align-items-center">
                        <div class="progress me-2" style="width: 100px;">
                            <div class="progress-bar" role="progressbar" style="width: ${workflow.progress || 0}%"></div>
                        </div>
                        <span>${Math.round(workflow.progress || 0)}%</span>
                    </div>
                </td>
                <td>
                    <div class="d-flex flex-wrap">
                        ${workflow.agents.map(agent => `
                            <span class="badge bg-secondary me-1 mb-1">${agent}</span>
                        `).join('')}
                    </div>
                </td>
                <td>
                    <small>${new Date(workflow.created_at).toLocaleString()}</small>
                </td>
                <td>
                    <button class="btn btn-sm btn-outline-primary btn-action" onclick="viewWorkflow('${workflow.id}')">
                        <i class="fas fa-eye"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger btn-action" onclick="stopWorkflow('${workflow.id}')">
                        <i class="fas fa-stop"></i>
                    </button>
                </td>
            `;
            tbody.appendChild(row);
        });
    }
    
    updateAlerts(data) {
        const container = document.getElementById('alerts-container');
        if (!container) return;
        
        container.innerHTML = '';
        
        const alerts = data.alerts || [];
        if (alerts.length === 0) {
            container.innerHTML = '<div class="alert alert-success">Aucune alerte active</div>';
            return;
        }
        
        alerts.forEach(alert => {
            const alertDiv = document.createElement('div');
            alertDiv.className = `alert alert-${this.getAlertClass(alert.type)} alert-dismissible`;
            alertDiv.innerHTML = `
                <strong>${alert.type.toUpperCase()}</strong> ${alert.message}
                <small class="d-block">
                    ${new Date(alert.timestamp * 1000).toLocaleString()}
                </small>
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            `;
            container.appendChild(alertDiv);
        });
    }
    
    // Utilitaires
    updateElement(id, value) {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = value;
        }
    }
    
    updateProgressBar(id, value) {
        const element = document.getElementById(id);
        if (element) {
            element.style.width = `${Math.round(value * 100)}%`;
        }
    }
    
    getHealthText(health) {
        const healthMap = {
            'healthy': 'Excellent',
            'warning': 'Attention',
            'critical': 'Critique'
        };
        return healthMap[health] || 'Inconnu';
    }
    
    getStatusClass(isHealthy) {
        return isHealthy ? 'status-healthy' : 'status-critical';
    }
    
    getStatusBadgeClass(status) {
        const statusMap = {
            'running': 'bg-success',
            'pending': 'bg-warning',
            'completed': 'bg-info',
            'failed': 'bg-danger'
        };
        return statusMap[status] || 'bg-secondary';
    }
    
    getAlertClass(type) {
        const typeMap = {
            'info': 'info',
            'warning': 'warning',
            'error': 'danger',
            'critical': 'danger'
        };
        return typeMap[type] || 'info';
    }
    
    formatMetricName(name) {
        return name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }
    
    formatMetricValue(value) {
        if (typeof value !== 'number') return value;
        
        if (value >= 1000000) {
            return (value / 1000000).toFixed(1) + 'M';
        } else if (value >= 1000) {
            return (value / 1000).toFixed(1) + 'K';
        } else if (value < 1) {
            return value.toFixed(3);
        } else {
            return value.toFixed(1);
        }
    }
    
    loadSectionData(sectionName) {
        switch (sectionName) {
            case 'agents':
                this.loadAgents();
                break;
            case 'workflows':
                this.loadWorkflows();
                break;
            case 'metrics':
                this.loadMetrics();
                break;
            case 'intelligence':
                this.loadIntelligenceData();
                break;
        }
    }
    
    async loadIntelligenceData() {
        try {
            const response = await fetch('/api/intelligence/metrics');
            const data = await response.json();
            this.updateIntelligenceSection(data);
        } catch (error) {
            console.error('Error loading intelligence data:', error);
        }
    }
    
    updateIntelligenceSection(data) {
        if (!data || data.error) return;
        
        const overall = data.overall_intelligence || {};
        
        // Score d'apprentissage
        const learningScore = Math.round((overall.adaptation_score || 0) * 100);
        this.updateElement('learning-score', `${learningScore}%`);
        this.updateProgressBar('learning-progress', learningScore / 100);
        
        // Stratégie actuelle
        this.updateElement('current-strategy', overall.current_strategy || 'Hybride');
        
        // Adaptations
        this.updateElement('adaptations-count', overall.total_tasks_processed || 0);
    }
    
    resizeCharts() {
        Object.values(this.charts).forEach(chart => {
            if (chart) {
                chart.resize();
            }
        });
    }
    
    startUpdateTimer() {
        // Mettre à jour l'heure de dernière mise à jour
        setInterval(() => {
            this.updateLastUpdateTime();
        }, 1000);
    }
    
    pauseUpdates() {
        // Logique pour mettre en pause les mises à jour
        console.log('Dashboard updates paused');
    }
    
    resumeUpdates() {
        // Logique pour reprendre les mises à jour
        console.log('Dashboard updates resumed');
        this.loadSectionData(this.currentSection);
    }
    
    showActionResult(data) {
        const alert = document.createElement('div');
        alert.className = 'alert alert-success alert-dismissible';
        alert.innerHTML = `
            <strong>Action réussie:</strong> ${data.message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        document.body.appendChild(alert);
        
        // Supprimer l'alerte après 5 secondes
        setTimeout(() => {
            alert.remove();
        }, 5000);
    }
    
    showAlert(data) {
        const alert = document.createElement('div');
        alert.className = `alert alert-${this.getAlertClass(data.type)} alert-dismissible`;
        alert.innerHTML = `
            <strong>${data.type.toUpperCase()}:</strong> ${data.message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        document.body.appendChild(alert);
    }
    
    updateStrategy(data) {
        this.updateElement('current-strategy', data.strategy);
        this.showActionResult(data);
    }
}

// Actions globales
let currentAction = null;

function scaleAgent(agentId, direction) {
    const action = direction === 'up' ? 'scale_up' : 'scale_down';
    currentAction = { agentId, action };
    
    document.getElementById('action-message').textContent = 
        `Voulez-vous vraiment ${action === 'scale_up' ? 'augmenter' : 'diminuer'} la capacité de l'agent ${agentId} ?`;
    
    new bootstrap.Modal(document.getElementById('actionModal')).show();
}

function restartAgent(agentId) {
    currentAction = { agentId, action: 'restart' };
    
    document.getElementById('action-message').textContent = 
        `Voulez-vous vraiment redémarrer l'agent ${agentId} ?`;
    
    new bootstrap.Modal(document.getElementById('actionModal')).show();
}

function viewWorkflow(workflowId) {
    // Rediriger vers la vue détaillée du workflow
    console.log('Viewing workflow:', workflowId);
}

function stopWorkflow(workflowId) {
    currentAction = { workflowId, action: 'stop' };
    
    document.getElementById('action-message').textContent = 
        `Voulez-vous vraiment arrêter le workflow ${workflowId} ?`;
    
    new bootstrap.Modal(document.getElementById('actionModal')).show();
}

function changeStrategy() {
    const strategies = ['performance_optimized', 'cost_efficient', 'quality_focused', 'hybrid'];
    const currentStrategy = document.getElementById('current-strategy').textContent.toLowerCase();
    const currentIndex = strategies.indexOf(currentStrategy);
    const nextStrategy = strategies[(currentIndex + 1) % strategies.length];
    
    currentAction = { strategy: nextStrategy, action: 'update_strategy' };
    
    document.getElementById('action-message').textContent = 
        `Changer la stratégie vers ${nextStrategy} ?`;
    
    new bootstrap.Modal(document.getElementById('actionModal')).show();
}

async function executeAction() {
    if (!currentAction) return;
    
    try {
        let response;
        
        if (currentAction.action === 'restart') {
            response = await fetch('/api/actions/restart_agent', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ agent_id: currentAction.agentId })
            });
        } else if (currentAction.action === 'scale_up' || currentAction.action === 'scale_down') {
            response = await fetch('/api/actions/scale_agent', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    agent_id: currentAction.agentId,
                    action: currentAction.action
                })
            });
        } else if (currentAction.action === 'update_strategy') {
            response = await fetch('/api/actions/update_strategy', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ strategy: currentAction.strategy })
            });
        }
        
        if (response && response.ok) {
            const result = await response.json();
            console.log('Action executed:', result);
        }
        
    } catch (error) {
        console.error('Error executing action:', error);
    }
    
    currentAction = null;
    bootstrap.Modal.getInstance(document.getElementById('actionModal')).hide();
}

// Initialisation
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new DashboardManager();
});