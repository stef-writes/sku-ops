import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { ShieldCheck, HardHat } from "lucide-react";
import { AuthLayout } from "../components/AuthLayout";

function LoginPanel({
  title,
  icon: Icon,
  accentClass,
  demoHint,
  testPrefix,
  onSubmit,
  loading,
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!email || !password) {
      toast.error("Please fill in all fields");
      return;
    }
    onSubmit(email, password);
  };

  return (
    <div className="bg-surface rounded-2xl p-8 shadow-soft-lg border border-border/70 backdrop-blur-sm flex flex-col">
      <div className={`flex items-center gap-3 mb-6`}>
        <div
          className={`w-9 h-9 rounded-lg flex items-center justify-center ${accentClass}`}
        >
          <Icon className="w-5 h-5" />
        </div>
        <h2 className="text-base font-semibold text-foreground">{title}</h2>
      </div>
      <form onSubmit={handleSubmit} className="space-y-4 flex-1">
        <div>
          <Label
            htmlFor={`${testPrefix}-email`}
            className="text-muted-foreground font-medium text-sm"
          >
            Email
          </Label>
          <Input
            id={`${testPrefix}-email`}
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
            className="input-field mt-2"
            data-testid={`${testPrefix}-email-input`}
          />
        </div>
        <div>
          <Label
            htmlFor={`${testPrefix}-password`}
            className="text-muted-foreground font-medium text-sm"
          >
            Password
          </Label>
          <Input
            id={`${testPrefix}-password`}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            className="input-field mt-2"
            data-testid={`${testPrefix}-password-input`}
          />
        </div>
        <Button
          type="submit"
          disabled={loading}
          className="w-full btn-primary h-11 text-sm mt-2"
          data-testid={`${testPrefix}-submit-btn`}
        >
          {loading ? "Signing in…" : "Sign in"}
        </Button>
      </form>
      {demoHint && (
        <p className="text-center mt-4 text-muted-foreground text-xs">
          {demoHint}
        </p>
      )}
    </div>
  );
}

const Login = () => {
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleLogin = async (email, password) => {
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
    <AuthLayout testId="login-page" wide>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
        <LoginPanel
          title="Admin / Warehouse"
          icon={ShieldCheck}
          accentClass="bg-accent/15 text-accent"
          demoHint="Demo: admin@demo.local / demo123"
          testPrefix="admin-login"
          onSubmit={handleLogin}
          loading={loading}
        />
        <LoginPanel
          title="Contractor"
          icon={HardHat}
          accentClass="bg-emerald-500/15 text-emerald-400"
          demoHint="Demo: contractor@demo.local / demo123"
          testPrefix="contractor-login"
          onSubmit={handleLogin}
          loading={loading}
        />
      </div>
      <p className="text-center mt-6 text-muted-foreground text-sm">
        Don&apos;t have an account?{" "}
        <Link
          to="/register"
          className="text-accent font-medium hover:text-accent transition-colors"
          data-testid="register-link"
        >
          Create one
        </Link>
      </p>
    </AuthLayout>
  );
};

export default Login;
