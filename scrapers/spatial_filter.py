import logging
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Predefined active dark store cluster hotspots for Mode B fallback.
# These represent high-density locations in Tier 1 Indian cities (>500 people/km²).
TIER1_CLUSTERS = {
    "Bengaluru": [
        {"lat": 12.9716, "lng": 77.5946, "name": "Indiranagar"},
        {"lat": 12.9102, "lng": 77.6450, "name": "HSR Layout"},
        {"lat": 12.9352, "lng": 77.6244, "name": "Koramangala"}
    ],
    "Mumbai": [
        {"lat": 19.0596, "lng": 72.8295, "name": "Bandra"},
        {"lat": 19.1136, "lng": 72.8697, "name": "Andheri"},
        {"lat": 19.1176, "lng": 72.9060, "name": "Powai"}
    ],
    "Delhi-NCR": [
        {"lat": 28.6304, "lng": 77.2177, "name": "Connaught Place"},
        {"lat": 28.4460, "lng": 77.0650, "name": "Gurugram Sec 45"},
        {"lat": 28.6258, "lng": 77.3792, "name": "Noida Sec 62"}
    ],
    "Pune": [
        {"lat": 18.5362, "lng": 73.8940, "name": "Koregaon Park"},
        {"lat": 18.5074, "lng": 73.8077, "name": "Kothrud"}
    ],
    "Hyderabad": [
        {"lat": 17.4401, "lng": 78.3489, "name": "Gachibowli"},
        {"lat": 17.4325, "lng": 78.4071, "name": "Jubilee Hills"}
    ],
    "Chennai": [
        {"lat": 13.0418, "lng": 80.2337, "name": "T. Nagar"},
        {"lat": 13.0063, "lng": 80.2574, "name": "Adyar"}
    ]
}

class SpatialFilterEngine:
    def __init__(self, raster_path=None, density_threshold=500.0):
        self.raster_path = raster_path
        self.density_threshold = density_threshold
        self.mode = "B"
        self.raster_dataset = None

        if self.raster_path:
            try:
                import rasterio
                self.raster_dataset = rasterio.open(self.raster_path)
                self.mode = "A"
                logger.info(f"Spatial Pre-filtering Engine initialized in Mode A (rasterio) using {raster_path}")
            except Exception as e:
                logger.warning(f"Failed to initialize rasterio Mode A ({e}). Falling back to Mode B (High-Fidelity Static Grid).")
                self.mode = "B"
        else:
            logger.info("Spatial Pre-filtering Engine initialized in Mode B (High-Fidelity Static Grid).")

    def check_density(self, lat: float, lng: float) -> bool:
        """
        Validates if coordinates pass our population density threshold.
        """
        if self.mode == "A" and self.raster_dataset:
            try:
                val = next(self.raster_dataset.sample([(lng, lat)]))
                density = float(val[0])
                logger.info(f"Coordinate ({lat}, {lng}) resolved density: {density:.2f} people/km²")
                return density >= self.density_threshold
            except Exception as e:
                logger.warning(f"Raster query failed for ({lat}, {lng}): {e}. Defaulting to True for safety.")
                return True
        else:
            # Mode B Fallback: Verify proximity to predefined Tier 1 clusters (within ~5.5km)
            for city, clusters in TIER1_CLUSTERS.items():
                for c in clusters:
                    dist = np.sqrt((c["lat"] - lat)**2 + (c["lng"] - lng)**2)
                    if dist <= 0.05:
                        logger.info(f"Coordinate ({lat}, {lng}) resolved in Mode B (Active {city} - {c['name']} Cluster)")
                        return True
            logger.info(f"Coordinate ({lat}, {lng}) failed density filter in Mode B.")
            return False

    def get_scan_coordinates(self, input_coordinates=None):
        """
        Processes a list of coordinates, returning only those that satisfy the density threshold.
        If no input coordinates are provided, returns the complete set of pre-calculated high-density dark store clusters.
        """
        if not input_coordinates:
            all_points = []
            for city, points in TIER1_CLUSTERS.items():
                for p in points:
                    all_points.append({
                        "latitude": p["lat"],
                        "longitude": p["lng"],
                        "city": city,
                        "name": p["name"]
                    })
            logger.info(f"Mode B generating default active scanning grid with {len(all_points)} high-density cluster coordinates.")
            return all_points

        filtered = []
        for coord in input_coordinates:
            lat = coord.get("latitude") or coord.get("lat")
            lng = coord.get("longitude") or coord.get("lng")
            if lat is not None and lng is not None:
                if self.check_density(lat, lng):
                    filtered.append(coord)
                    
        reduction = (1.0 - (len(filtered) / len(input_coordinates))) * 100 if input_coordinates else 0.0
        logger.info(f"Spatial demographics filtering complete. Scanned grid reduced by {reduction:.1f}% ({len(filtered)}/{len(input_coordinates)} coordinates remain).")
        return filtered

    def close(self):
        if self.raster_dataset:
            try:
                self.raster_dataset.close()
                logger.info("Closed raster dataset.")
            except Exception:
                pass
