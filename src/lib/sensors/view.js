// OpenHAB Item evidence only; the browser never reaches a radio transport.
const MAX_BYTES=1048576;
export function sensorView(raw,now=Date.now(),connection='offline',service='online') {
 const empty={available:false,sensors:[],recent_events:[],daily_durations:[],environmental:[],operations:{}};
 if(typeof raw!=='string'||raw.length>MAX_BYTES) return empty;
 let view;try {view=JSON.parse(raw);} catch {return empty;}
 if(view?.schema!=='earthship-sensor-view/v1'||!['simulation','production'].includes(view.environment)||
    view.authority!=='observation_only'||!Array.isArray(view.sensors)||view.sensors.length>256||
    !Number.isFinite(Date.parse(view.generated_at))||Date.parse(view.generated_at)>now||
    !Number.isFinite(Date.parse(view.expires_at))||Date.parse(view.expires_at)<=Date.parse(view.generated_at)||
    Date.parse(view.expires_at)-Date.parse(view.generated_at)>45000) return empty;
 const ids=new Set();
 for(const sensor of view.sensors) {
  if(typeof sensor.sensor_id!=='string'||ids.has(sensor.sensor_id)||!['OPEN','CLOSED','UNKNOWN'].includes(sensor.current_state)||
    !['OPEN','CLOSED',null].includes(sensor.contact_state)||!['ONLINE','STALE','OFFLINE','UNKNOWN'].includes(sensor.health)||
    typeof sensor.valid!=='boolean'||['name','location','zone','device_type'].some(k=>typeof sensor[k]!=='string'||sensor[k].length>128)) return empty;
  const battery=sensor.battery;
  if(!battery||typeof battery!=='object'||!['OK','LOW','UNKNOWN'].includes(battery.condition)||
     (battery.percent!=null&&(!Number.isFinite(battery.percent)||battery.percent<0||battery.percent>100))||
     (battery.volts!=null&&(!Number.isFinite(battery.volts)||battery.volts<0||battery.volts>10)))return empty;
  ids.add(sensor.sensor_id);
 }
 const sourceLive=service==='online'&&connection==='live'&&now<Date.parse(view.expires_at);
 const sensors=view.sensors.map(sensor=>{
  const offline=Number.isFinite(Date.parse(sensor.offline_at))&&now>=Date.parse(sensor.offline_at);
  const commFresh=Number.isFinite(Date.parse(sensor.communication_valid_until))&&now<Date.parse(sensor.communication_valid_until);
  const observed=Date.parse(sensor.last_observed_at);
  const valid=sourceLive&&sensor.valid&&sensor.health==='ONLINE'&&commFresh&&
    Number.isFinite(observed)&&observed<=now&&now<Date.parse(sensor.valid_until);
  const health=offline?'OFFLINE':!sourceLive||!commFresh?(sensor.health==='UNKNOWN'?'UNKNOWN':'STALE'):sensor.health;
  return {...sensor,current_state:valid?sensor.current_state:'UNKNOWN',valid,health};
 });
 return {...view,available:true,sourceLive,sensors,
  recent_events:Array.isArray(view.recent_events)?view.recent_events.filter(e=>e&&typeof e.sensor_id==='string'&&typeof e.event_type==='string'&&Number.isFinite(Date.parse(e.observed_at))).slice(0,48):[],
  daily_durations:Array.isArray(view.daily_durations)?view.daily_durations.filter(e=>e&&typeof e.sensor_id==='string'&&typeof e.date==='string'&&Number.isFinite(e.open_seconds)&&e.open_seconds>=0).slice(0,256):[],
  environmental:Array.isArray(view.environmental)?view.environmental.filter(e=>e&&typeof e.sensor_id==='string'&&typeof e.observation_type==='string'&&typeof e.unit==='string'&&['number','boolean','string'].includes(typeof e.value)).slice(0,256):[],operations:view.operations||{}};
}
export function counts(sensors) {
 const result={windows:0,skylights:0,doors:0,closed:0,unknown:0,offline:0};
 for(const s of sensors) {
  if(s.health==='OFFLINE')result.offline++;
  if(s.current_state==='UNKNOWN')result.unknown++;
  else if(s.current_state==='CLOSED')result.closed++;
  else if(s.device_type==='window')result.windows++;
  else if(s.device_type==='skylight')result.skylights++;
  else if(s.device_type==='door')result.doors++;
 }
 return result;
}
export function since(raw,now) {
 const t=Date.parse(raw);if(!Number.isFinite(t)||t>now)return 'unknown';
 const seconds=Math.floor((now-t)/1000);
 return seconds<60?`${seconds}s ago`:seconds<3600?`${Math.floor(seconds/60)}m ago`:`${Math.floor(seconds/3600)}h ago`;
}
