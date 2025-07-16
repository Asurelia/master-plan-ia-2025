-- Master Plan IA 2025 - Création des tables Supabase
-- Ce fichier contient les requêtes SQL pour créer toutes les tables nécessaires

-- Activer l'extension UUID
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Table des agents
CREATE TABLE IF NOT EXISTS public.agents (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'inactive',
    capabilities JSONB DEFAULT '[]'::jsonb,
    config JSONB DEFAULT '{}'::jsonb,
    current_tasks INTEGER DEFAULT 0,
    max_concurrent_tasks INTEGER DEFAULT 3,
    is_healthy BOOLEAN DEFAULT true,
    last_heartbeat TIMESTAMP WITH TIME ZONE DEFAULT now(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Table des tâches
CREATE TABLE IF NOT EXISTS public.tasks (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    agent_id UUID REFERENCES public.agents(id) ON DELETE CASCADE,
    workflow_id UUID DEFAULT NULL,
    type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    priority INTEGER DEFAULT 5,
    payload JSONB DEFAULT '{}'::jsonb,
    result JSONB DEFAULT '{}'::jsonb,
    error_message TEXT DEFAULT NULL,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    completed_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Table des workflows
CREATE TABLE IF NOT EXISTS public.workflows (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    name TEXT NOT NULL,
    pattern TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    config JSONB DEFAULT '{}'::jsonb,
    agents JSONB DEFAULT '[]'::jsonb,
    steps JSONB DEFAULT '[]'::jsonb,
    current_step INTEGER DEFAULT 0,
    results JSONB DEFAULT '{}'::jsonb,
    context JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Table des métriques
CREATE TABLE IF NOT EXISTS public.metrics (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    name TEXT NOT NULL,
    value NUMERIC NOT NULL,
    unit TEXT DEFAULT NULL,
    tags JSONB DEFAULT '{}'::jsonb,
    metadata JSONB DEFAULT '{}'::jsonb,
    agent_id UUID REFERENCES public.agents(id) ON DELETE CASCADE DEFAULT NULL,
    workflow_id UUID REFERENCES public.workflows(id) ON DELETE CASCADE DEFAULT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Table des plugins
CREATE TABLE IF NOT EXISTS public.plugins (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    version TEXT NOT NULL,
    type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'inactive',
    config JSONB DEFAULT '{}'::jsonb,
    metrics JSONB DEFAULT '{}'::jsonb,
    load_time NUMERIC DEFAULT NULL,
    error_message TEXT DEFAULT NULL,
    manifest JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Table des utilisateurs (pour l'authentification)
CREATE TABLE IF NOT EXISTS public.users (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    profile JSONB DEFAULT '{}'::jsonb,
    is_active BOOLEAN DEFAULT true,
    last_login TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Table des sessions
CREATE TABLE IF NOT EXISTS public.sessions (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
    token TEXT NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    user_agent TEXT DEFAULT NULL,
    ip_address INET DEFAULT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Table des logs système
CREATE TABLE IF NOT EXISTS public.system_logs (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    component TEXT NOT NULL,
    details JSONB DEFAULT '{}'::jsonb,
    user_id UUID REFERENCES public.users(id) ON DELETE SET NULL DEFAULT NULL,
    agent_id UUID REFERENCES public.agents(id) ON DELETE SET NULL DEFAULT NULL,
    workflow_id UUID REFERENCES public.workflows(id) ON DELETE SET NULL DEFAULT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT now(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Table d'audit trail
CREATE TABLE IF NOT EXISTS public.audit_trail (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id UUID NOT NULL,
    old_values JSONB DEFAULT '{}'::jsonb,
    new_values JSONB DEFAULT '{}'::jsonb,
    user_id UUID REFERENCES public.users(id) ON DELETE SET NULL DEFAULT NULL,
    ip_address INET DEFAULT NULL,
    user_agent TEXT DEFAULT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT now(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Table des configurations
CREATE TABLE IF NOT EXISTS public.configurations (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,
    value JSONB NOT NULL,
    description TEXT DEFAULT NULL,
    is_encrypted BOOLEAN DEFAULT false,
    category TEXT DEFAULT 'general',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Table des webhooks
CREATE TABLE IF NOT EXISTS public.webhooks (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    url TEXT NOT NULL,
    events JSONB DEFAULT '[]'::jsonb,
    secret TEXT DEFAULT NULL,
    headers JSONB DEFAULT '{}'::jsonb,
    timeout INTEGER DEFAULT 30,
    max_retries INTEGER DEFAULT 3,
    retry_delay INTEGER DEFAULT 5,
    is_active BOOLEAN DEFAULT true,
    description TEXT DEFAULT NULL,
    filters JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Table des livraisons de webhooks
CREATE TABLE IF NOT EXISTS public.webhook_deliveries (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    webhook_id UUID REFERENCES public.webhooks(id) ON DELETE CASCADE,
    event TEXT NOT NULL,
    payload JSONB NOT NULL,
    url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    response_status INTEGER DEFAULT NULL,
    response_body TEXT DEFAULT NULL,
    error_message TEXT DEFAULT NULL,
    next_retry TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    delivered_at TIMESTAMP WITH TIME ZONE DEFAULT NULL
);

-- Index pour optimiser les performances
CREATE INDEX IF NOT EXISTS idx_agents_status ON public.agents(status);
CREATE INDEX IF NOT EXISTS idx_agents_type ON public.agents(type);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON public.tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_agent_id ON public.tasks(agent_id);
CREATE INDEX IF NOT EXISTS idx_tasks_workflow_id ON public.tasks(workflow_id);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON public.tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_workflows_status ON public.workflows(status);
CREATE INDEX IF NOT EXISTS idx_metrics_name ON public.metrics(name);
CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON public.metrics(timestamp);
CREATE INDEX IF NOT EXISTS idx_metrics_agent_id ON public.metrics(agent_id);
CREATE INDEX IF NOT EXISTS idx_plugins_name ON public.plugins(name);
CREATE INDEX IF NOT EXISTS idx_plugins_status ON public.plugins(status);
CREATE INDEX IF NOT EXISTS idx_system_logs_level ON public.system_logs(level);
CREATE INDEX IF NOT EXISTS idx_system_logs_timestamp ON public.system_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_trail_entity_type ON public.audit_trail(entity_type);
CREATE INDEX IF NOT EXISTS idx_audit_trail_entity_id ON public.audit_trail(entity_id);
CREATE INDEX IF NOT EXISTS idx_configurations_key ON public.configurations(key);
CREATE INDEX IF NOT EXISTS idx_webhooks_url ON public.webhooks(url);
CREATE INDEX IF NOT EXISTS idx_webhooks_is_active ON public.webhooks(is_active);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_webhook_id ON public.webhook_deliveries(webhook_id);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_status ON public.webhook_deliveries(status);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_created_at ON public.webhook_deliveries(created_at);

-- Triggers pour updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_agents_updated_at BEFORE UPDATE ON public.agents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_tasks_updated_at BEFORE UPDATE ON public.tasks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_workflows_updated_at BEFORE UPDATE ON public.workflows
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_plugins_updated_at BEFORE UPDATE ON public.plugins
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON public.users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_configurations_updated_at BEFORE UPDATE ON public.configurations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_webhooks_updated_at BEFORE UPDATE ON public.webhooks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Politiques RLS (Row Level Security) - Optionnel pour plus de sécurité
-- ALTER TABLE public.agents ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE public.tasks ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE public.workflows ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE public.metrics ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE public.plugins ENABLE ROW LEVEL SECURITY;

-- Insérer des données de test
INSERT INTO public.agents (name, type, status, capabilities, config) VALUES
    ('LLM Session Agent', 'llm_session', 'active', '["text_generation", "analysis", "translation"]', '{"max_tokens": 4096}'),
    ('Claude Code Agent', 'claude_code', 'active', '["code_generation", "debugging", "refactoring"]', '{"language": "python"}'),
    ('Ollama Agent', 'ollama', 'active', '["chat", "embeddings", "local_processing"]', '{"model": "llama2"}')
ON CONFLICT (name) DO NOTHING;

INSERT INTO public.configurations (key, value, description, category) VALUES
    ('system.max_concurrent_tasks', '10', 'Maximum number of concurrent tasks', 'system'),
    ('cache.redis.enabled', 'true', 'Enable Redis cache', 'cache'),
    ('plugins.auto_load', 'true', 'Auto-load plugins on startup', 'plugins'),
    ('auth.jwt.secret', '"your-jwt-secret-here"', 'JWT secret for authentication', 'auth'),
    ('monitoring.metrics.retention_days', '30', 'Metrics retention period in days', 'monitoring')
ON CONFLICT (key) DO NOTHING;

-- Vues utiles pour le monitoring
CREATE OR REPLACE VIEW public.agent_stats AS
SELECT 
    a.id,
    a.name,
    a.type,
    a.status,
    a.current_tasks,
    a.max_concurrent_tasks,
    ROUND((a.current_tasks::decimal / a.max_concurrent_tasks::decimal) * 100, 2) as load_percentage,
    COUNT(t.id) as total_tasks,
    COUNT(CASE WHEN t.status = 'completed' THEN 1 END) as completed_tasks,
    COUNT(CASE WHEN t.status = 'failed' THEN 1 END) as failed_tasks,
    a.created_at,
    a.updated_at
FROM public.agents a
LEFT JOIN public.tasks t ON a.id = t.agent_id
GROUP BY a.id, a.name, a.type, a.status, a.current_tasks, a.max_concurrent_tasks, a.created_at, a.updated_at;

CREATE OR REPLACE VIEW public.workflow_stats AS
SELECT 
    w.id,
    w.name,
    w.pattern,
    w.status,
    w.current_step,
    jsonb_array_length(w.steps) as total_steps,
    ROUND((w.current_step::decimal / GREATEST(jsonb_array_length(w.steps), 1)::decimal) * 100, 2) as progress_percentage,
    COUNT(t.id) as total_tasks,
    COUNT(CASE WHEN t.status = 'completed' THEN 1 END) as completed_tasks,
    w.created_at,
    w.updated_at
FROM public.workflows w
LEFT JOIN public.tasks t ON w.id = t.workflow_id
GROUP BY w.id, w.name, w.pattern, w.status, w.current_step, w.steps, w.created_at, w.updated_at;

CREATE OR REPLACE VIEW public.recent_metrics AS
SELECT 
    m.name,
    m.value,
    m.unit,
    m.tags,
    a.name as agent_name,
    w.name as workflow_name,
    m.timestamp,
    m.created_at
FROM public.metrics m
LEFT JOIN public.agents a ON m.agent_id = a.id
LEFT JOIN public.workflows w ON m.workflow_id = w.id
WHERE m.timestamp >= now() - interval '1 hour'
ORDER BY m.timestamp DESC;

-- Fonction pour nettoyer les anciennes métriques
CREATE OR REPLACE FUNCTION cleanup_old_metrics(retention_days INTEGER DEFAULT 30)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM public.metrics 
    WHERE timestamp < now() - (retention_days || ' days')::interval;
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    
    INSERT INTO public.system_logs (level, message, component, details)
    VALUES ('info', 'Cleaned up old metrics', 'maintenance', 
            jsonb_build_object('deleted_count', deleted_count, 'retention_days', retention_days));
    
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Fonction pour obtenir les statistiques système
CREATE OR REPLACE FUNCTION get_system_stats()
RETURNS JSONB AS $$
BEGIN
    RETURN jsonb_build_object(
        'agents', jsonb_build_object(
            'total', (SELECT COUNT(*) FROM public.agents),
            'active', (SELECT COUNT(*) FROM public.agents WHERE status = 'active'),
            'inactive', (SELECT COUNT(*) FROM public.agents WHERE status = 'inactive')
        ),
        'tasks', jsonb_build_object(
            'total', (SELECT COUNT(*) FROM public.tasks),
            'pending', (SELECT COUNT(*) FROM public.tasks WHERE status = 'pending'),
            'running', (SELECT COUNT(*) FROM public.tasks WHERE status = 'running'),
            'completed', (SELECT COUNT(*) FROM public.tasks WHERE status = 'completed'),
            'failed', (SELECT COUNT(*) FROM public.tasks WHERE status = 'failed')
        ),
        'workflows', jsonb_build_object(
            'total', (SELECT COUNT(*) FROM public.workflows),
            'active', (SELECT COUNT(*) FROM public.workflows WHERE status = 'running'),
            'completed', (SELECT COUNT(*) FROM public.workflows WHERE status = 'completed')
        ),
        'metrics', jsonb_build_object(
            'total', (SELECT COUNT(*) FROM public.metrics),
            'last_hour', (SELECT COUNT(*) FROM public.metrics WHERE timestamp >= now() - interval '1 hour')
        ),
        'plugins', jsonb_build_object(
            'total', (SELECT COUNT(*) FROM public.plugins),
            'active', (SELECT COUNT(*) FROM public.plugins WHERE status = 'active')
        )
    );
END;
$$ LANGUAGE plpgsql;