-- Fonction pour exécuter des requêtes SQL via RPC
CREATE OR REPLACE FUNCTION public.exec_sql(query text)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    EXECUTE query;
    RETURN 'OK';
EXCEPTION
    WHEN OTHERS THEN
        RETURN SQLERRM;
END;
$$;