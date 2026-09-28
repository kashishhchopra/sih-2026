// ISO 3166-1 alpha-2 codes matching backend/app/data/reference/embassies.json
// -- kept in sync manually since both are small, curated lists rather than
// a live country-code API call. Used by Register.jsx's passport flow so a
// foreign tourist's nationality resolves to a code the backend's consular
// lookup (services/consular.py) can actually match.
export const COUNTRIES = [
  { code: 'US', name: 'United States' },
  { code: 'GB', name: 'United Kingdom' },
  { code: 'JP', name: 'Japan' },
  { code: 'KR', name: 'South Korea' },
  { code: 'CN', name: 'China' },
  { code: 'FR', name: 'France' },
  { code: 'DE', name: 'Germany' },
  { code: 'ES', name: 'Spain' },
  { code: 'RU', name: 'Russia' },
  { code: 'SA', name: 'Saudi Arabia' },
  { code: 'AE', name: 'United Arab Emirates' },
  { code: 'PT', name: 'Portugal' },
  { code: 'IT', name: 'Italy' },
  { code: 'AU', name: 'Australia' },
  { code: 'CA', name: 'Canada' },
  { code: 'NL', name: 'Netherlands' },
  { code: 'SG', name: 'Singapore' },
  { code: 'TH', name: 'Thailand' },
  { code: 'IL', name: 'Israel' },
  { code: 'BD', name: 'Bangladesh' },
  { code: 'NP', name: 'Nepal' },
  { code: 'OTHER', name: 'Other / not listed' },
]
