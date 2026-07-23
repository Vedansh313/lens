const users = [
  { email: "demo@lens.app", password: "demo123", name: "Demo User" },
  { email: "admin@lens.app", password: "lens2024", name: "Admin" },
];

export function authenticate(email, password) {
  const normalized = email.trim().toLowerCase();
  const user = users.find(
    (entry) => entry.email === normalized && entry.password === password
  );
  if (!user) return null;
  return { email: user.email, name: user.name };
}
