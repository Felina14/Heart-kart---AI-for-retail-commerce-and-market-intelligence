export function getApiBaseUrl(): string {
  const envUrl = process.env.NEXT_PUBLIC_API_URL
  if (envUrl && envUrl.trim()) return envUrl

  // When running locally (or on LAN), default to the same hostname as the UI
  // but with backend port 5000.
  if (typeof window !== 'undefined') {
    const host = window.location.hostname || 'localhost'
    const protocol = window.location.protocol || 'http:'
    return `${protocol}//${host}:5000`
  }

  // Server-side fallback
  return 'http://localhost:5000'
}

