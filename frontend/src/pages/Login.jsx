import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Wrench, LogIn } from "lucide-react";

const Login = () => {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email || !password) {
      toast.error("Please fill in all fields");
      return;
    }

    setLoading(true);
    try {
      await login(email, password);
      toast.success("Welcome back!");
      navigate("/");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="min-h-screen flex items-center justify-center p-6 bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900"
      data-testid="login-page"
    >
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-amber-500/5 via-transparent to-transparent" />
      <div className="w-full max-w-md relative">
        {/* Logo */}
        <div className="text-center mb-10">
          <div className="w-14 h-14 bg-gradient-to-br from-amber-400 to-orange-500 rounded-xl mx-auto flex items-center justify-center mb-5 shadow-soft">
            <Wrench className="w-7 h-7 text-white" />
          </div>
          <h1 className="text-2xl font-semibold text-white tracking-tight">
            Supply Yard
          </h1>
          <p className="text-slate-400 mt-2 text-sm">
            Material management for contractors & warehouses
          </p>
        </div>

        {/* Login Form */}
        <div className="bg-white rounded-2xl p-8 shadow-soft-lg border border-slate-200/50">
          <h2 className="text-lg font-semibold text-slate-900 mb-6">
            Sign in to your account
          </h2>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <Label
                htmlFor="email"
                className="text-slate-600 font-medium text-sm"
              >
                Email
              </Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                className="input-field mt-2"
                data-testid="login-email-input"
              />
            </div>

            <div>
              <Label
                htmlFor="password"
                className="text-slate-600 font-medium text-sm"
              >
                Password
              </Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="input-field mt-2"
                data-testid="login-password-input"
              />
            </div>

            <Button
              type="submit"
              disabled={loading}
              className="w-full btn-primary h-11 text-sm"
              data-testid="login-submit-btn"
            >
              <LogIn className="w-4 h-4 mr-2" />
              {loading ? "Signing in…" : "Sign in"}
            </Button>
          </form>

          <p className="text-center mt-4 text-slate-400 text-xs">
            Demo: admin@demo.local / demo123
          </p>
          <p className="text-center mt-6 text-slate-500 text-sm">
            Don't have an account?{" "}
            <Link
              to="/register"
              className="text-amber-600 font-medium hover:text-amber-700 transition-colors"
              data-testid="register-link"
            >
              Create one
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
};

export default Login;
