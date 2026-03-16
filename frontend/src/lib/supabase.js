const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || "";
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || "";

/**
 * True when Supabase credentials are present in the environment.
 * When false, AuthContext falls back to /api/auth/login bridge mode.
 */
export const isSupabaseConfigured = Boolean(supabaseUrl && supabaseAnonKey);

let _supabase = null;

export const getSupabase = async () => {
  if (!_supabase && isSupabaseConfigured) {
    const { createClient } = await import("@supabase/supabase-js");
    _supabase = createClient(supabaseUrl, supabaseAnonKey);
  }
  return _supabase;
};
