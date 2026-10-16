// Cloudflare Worker: Telegram inline menu webhook.
// Bind KV namespace MENU_STATE; set BOT_TOKEN, WEBHOOK_SECRET, CHAT_ID as secrets/vars.
const TIMES = [[5,45,"AUSTRALIA"],[7,45,"LAOS"],[8,0,"SOUTHKOREA"],[8,30,"NORTHKOREA"],[8,35,"NEW YORK"],[9,10,"KENTUCKY EVENING"],[9,20,"TEXAS"],[10,45,"CAMBODIA"],[11,15,"BRUNEI"],[11,20,"BULLSEYE"],[12,15,"TTM 13"],[12,45,"SYDNEY"],[13,45,"NEWZEALAND"],[14,30,"CHINA"],[15,15,"TTM 16"],[16,15,"JAPAN"],[16,45,"SGP"],[17,15,"MAGNUM4D"],[17,40,"MEXICO"],[18,15,"TTM 19"],[19,15,"PCSO"],[19,45,"TAIWAN"],[21,15,"TTM 22"],[21,45,"HONGKONG"],[22,15,"TTM 23"],[23,15,"TTM 24"],[23,30,"KENTUCKY DAY"]];
const menu = {inline_keyboard: [[{text:"📋 LIST PASARAN",callback_data:"menu:list"},{text:"📊 PROGRESS",callback_data:"menu:progress"}]]};
const back = {inline_keyboard: [[{text:"⬅️ KEMBALI",callback_data:"menu:back"}]]};
const off = (n,d) => n==="SGP" ? [2,5].includes(d) : n==="MAGNUM4D" && ![3,6,0].includes(d);
function listText() {
  return ["📋 DAFTAR PASARAN","━━━━━━━━━━━━━━━━━━",...TIMES.map(([,,n],i)=>String(i+1).padStart(2,"0")+". "+n+(n==="SGP"?" (OFF: Selasa, Jumat)":n==="MAGNUM4D"?" (OFF: Senin, Selasa, Kamis, Jumat)":"")),"━━━━━━━━━━━━━━━━━━","📊 TOTAL: "+TIMES.length+" PASARAN"].join("\n");
}
function progressText() {
  const now=new Date();
  const parts=Object.fromEntries(new Intl.DateTimeFormat("en-GB",{timeZone:"Asia/Jakarta",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hourCycle:"h23",weekday:"short"}).formatToParts(now).map(p=>[p.type,p.value]));
  const days={Sun:0,Mon:1,Tue:2,Wed:3,Thu:4,Fri:5,Sat:6};
  const day=days[parts.weekday],mins=Number(parts.hour)*60+Number(parts.minute);
  const done=[],pending=[],rest=[];
  for(const [h,m,n] of TIMES) (off(n,day)?rest:mins>=h*60+m+30?done:pending).push(n);
  return ["📊 PROGRESS PREDIKSI HARI INI",`🕒 ${parts.day}/${parts.month}/${parts.year} ${parts.hour}:${parts.minute} WIB`,"━━━━━━━━━━━━━━━━━━",...[[ "✅ SUDAH PREDIKSI",done],["⏳ BELUM PREDIKSI",pending],["💤 OFF HARI INI",rest]].flatMap(([title,names])=>["",`${title} (${names.length})`,...names]),"","━━━━━━━━━━━━━━━━━━",`📊 TOTAL AKTIF: ${done.length+pending.length} PASARAN`].join("\n");
}
async function telegram(env,method,payload) {
  const response=await fetch(`https://api.telegram.org/bot${env.BOT_TOKEN}/${method}`,{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(payload)});
  const data=await response.json();
  if(!data.ok) throw Error(`${method}: ${data.description}`);
  return data.result;
}
export default {
  async fetch(request,env) {
    if(request.method!=="POST" || request.headers.get("X-Telegram-Bot-Api-Secret-Token")!==env.WEBHOOK_SECRET) return new Response("Forbidden",{status:403});
    try {
      const update=await request.json(),q=update.callback_query;
      if(!q) return new Response("OK");
      const msg=q.message,chat=msg?.chat?.id,id=msg?.message_id;
      if(!chat || String(chat)!==String(env.CHAT_ID) || !id) { await telegram(env,"answerCallbackQuery",{callback_query_id:q.id}); return new Response("OK"); }
      const key=`original:${chat}:${id}`,action=q.data;
      if(action==="menu:list" || action==="menu:progress") {
        let original=await env.MENU_STATE.get(key);
        if(!original && msg.text?.startsWith("🔮 PREDIKSI ")) {
          original=msg.text;
          await env.MENU_STATE.put(key,original,{expirationTtl:604800});
        }
        if(original) await telegram(env,"editMessageText",{chat_id:chat,message_id:id,text:action==="menu:list"?listText():progressText(),reply_markup:back});
      } else if(action==="menu:back") {
        const original=await env.MENU_STATE.get(key);
        if(original) await telegram(env,"editMessageText",{chat_id:chat,message_id:id,text:original,reply_markup:menu});
      }
      await telegram(env,"answerCallbackQuery",{callback_query_id:q.id});
      return new Response("OK");
    } catch(err) { console.error(err); return new Response("Callback error",{status:500}); }
  }
};
