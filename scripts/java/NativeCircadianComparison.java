import java.time.*;
import java.util.*;
import org.openhab.binding.astro.internal.calc.SunCalc;
import org.openhab.binding.astro.internal.calc.CircadianCalc;
import org.openhab.binding.astro.internal.model.SunPhase;
class NativeCircadianComparison {
  static Calendar at(Instant at, ZoneId zone) { return GregorianCalendar.from(at.atZone(zone)); }
  public static void main(String[] args) {
    ZoneId zone=ZoneId.of("America/Denver");
    double lat=38.3739919, lon=-105.7744609;
    for (String day : new String[]{"2026-06-21", "2026-12-21"}) {
      Instant midnight=LocalDate.parse(day).atStartOfDay(zone).toInstant();
      SunCalc calc=new SunCalc(InstantSource.fixed(midnight));
      var sun=calc.getSunInfo(at(midnight,zone),lat,lon,null,false,TimeZone.getTimeZone(zone),Locale.US);
      var rise=sun.getRange(SunPhase.SUN_RISE).getStart();
      var set=sun.getRange(SunPhase.SUN_SET).getStart();
      var noon=sun.getRange(SunPhase.NOON).getStart();
      var instants=new LinkedHashMap<String,Instant>();
      instants.put("midnight",midnight);
      instants.put("before_sunrise",rise.toInstant().minusSeconds(1));
      instants.put("sunrise",rise.toInstant());
      instants.put("after_sunrise",rise.toInstant().plusSeconds(1));
      instants.put("morning_midpoint",rise.toInstant().plusMillis((noon.getTimeInMillis()-rise.getTimeInMillis())/2));
      instants.put("transit",noon.toInstant());
      instants.put("before_sunset",set.toInstant().minusSeconds(1));
      instants.put("sunset",set.toInstant());
      instants.put("after_sunset",set.toInstant().plusSeconds(1));
      instants.put("solar_midnight",noon.toInstant().plusSeconds(43200));
      for (var entry:instants.entrySet()) {
        var point=at(entry.getValue(),zone);
        var nativeValue=CircadianCalc.calculate(point,rise,set,noon);
        double elevation=calc.getPosition(point,lat,lon).getElevationAsDouble();
        long legacy=2500+Math.round(Math.max(0,Math.min(50,elevation))*80);
        if(nativeValue.temperature()<2500||nativeValue.temperature()>5500)throw new AssertionError("native range");
        if(entry.getKey().equals("transit") && nativeValue.temperature()!=5500)throw new AssertionError("transit");
        System.out.println(day+"\t"+entry.getKey()+"\t"+entry.getValue()+"\t"+nativeValue.temperature()+"\t"+nativeValue.brightness()+"\t"+legacy+"\t"+elevation);
      }
    }
  }
}
