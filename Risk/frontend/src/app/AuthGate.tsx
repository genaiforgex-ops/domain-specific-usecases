import { LoginPage } from "../modules/LoginPage";

/** Unauthenticated entry — always email/password login. */
export function AuthGate() {
  return <LoginPage />;
}
