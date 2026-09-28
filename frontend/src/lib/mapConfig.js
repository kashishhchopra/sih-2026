// Shared Leaflet basemap config for every map in the app.
//
// OpenStreetMap's own {s}.tile.openstreetmap.org servers are volunteer-run
// and enforce a strict usage policy (osm.wiki/Blocked) that blocks apps
// making frequent/uncached requests -- exactly what a live-tracking
// dashboard with several open maps does. CARTO's basemap tiles later turned
// out to require a paid/free-tier API key we don't have (basemaps stopped
// resolving and showed an "API KEY REQUIRED" watermark instead). Esri's
// World Street Map tiles are free, need no key or signup, and are meant for
// exactly this kind of app usage.
export const TILE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}";
export const TILE_ATTRIBUTION =
  "Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community";
export const TILE_SUBDOMAINS = [];
