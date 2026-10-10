// Synthetic shape fixtures only; they do not establish household qualification.
import { rawInstalledPublication } from './installed-publication.js';
export function compressedInstalledPublication(mode = 'forecast_active', base = false) {
  const value = rawInstalledPublication(mode);
  value.schema = 'earthship-installed-shade-publication/v4'; value.version = 7;
  value.release.schema = 'earthship-installed-shade-release/v4';
  value.release.nativeOriginBindingSha256 = mode === 'unavailable' ? null : '1'.repeat(64);
  value.release.sourceQualificationSchema = mode === 'unavailable' ? null : 'earthship-installed-shade-qualification-report/v7';
  if (value.forecast) {
    value.forecast.schema = base ? 'earthship-installed-shade-forecast/v6' : 'earthship-installed-shade-forecast/v7';
    value.forecast.native_origin_binding_sha256 = value.release.nativeOriginBindingSha256;
  }
  if (base) {
    value.status = 'shadow'; value.confidence.grade = 'low'; value.release.forecastQualified = false;
    value.release.expiresAt = null; value.release.policySha256 = null; value.release.calibrationSha256 = null;
    value.release.sourceQualificationSchema = null; value.forecast.prediction_intervals = null;
  }
  return value;
}
