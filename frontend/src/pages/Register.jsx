import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { UserPlus } from "lucide-react";
import { AuthLayout } from "../components/AuthLayout";

const Register = () => {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const { register } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!name || !email || !password) { toast.error("Please fill in all fields"); return; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { toast.error("Please enter a valid email address"); return; }
    if (password !== confirmPassword) { toast.error("Passwords do not match"); return; }
    if (password.length < 6) { toast.error("Password must be at least 6 characters"); return; }
    setLoading(true);
    try {
      await register(email, password, name);
      toast.success("Account created successfully!");
      navigate("/");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout testId="register-page">
      <h2 className="text-lg font-semibold text-slate-900 mb-6">Create your account</h2>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <Label htmlFor="name" className="text-slate-600 font-medium text-sm">Full name</Label>
          <Input id="name" type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="John Doe" className="input-field mt-2" data-testid="register-name-input" />
        </div>
        <div>
          <Label htmlFor="email" className="text-slate-600 font-medium text-sm">Email</Label>
          <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" className="input-field mt-2" data-testid="register-email-input" />
        </div>
        <div>
          <Label htmlFor="password" className="text-slate-600 font-medium text-sm">Password</Label>
          <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" className="input-field mt-2" data-testid="register-password-input" />
        </div>
        <div>
          <Label htmlFor="confirmPassword" className="text-slate-600 font-medium text-sm">Confirm password</Label>
          <Input id="confirmPassword" type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} placeholder="••••••••" className="input-field mt-2" data-testid="register-confirm-password-input" />
        </div>
        <Button type="submit" disabled={loading} className="w-full btn-primary h-11 text-sm" data-testid="register-submit-btn">
          <UserPlus className="w-4 h-4 mr-2" />
          {loading ? "Creating account…" : "Create account"}
        </Button>
      </form>
      <p className="text-center mt-6 text-slate-500 text-sm">
        Already have an account?{" "}
        <Link to="/login" className="text-amber-600 font-medium hover:text-amber-700 transition-colors" data-testid="login-link">Sign in</Link>
      </p>
    </AuthLayout>
  );
};

export default Register;
