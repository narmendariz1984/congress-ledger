/* Congress Legislation Tracker: readable names, measure codes and state lookups.
   Shared by the page (site/index.html), the tests (tests/names.test.mjs) and the
   data quality check (scripts/check.mjs). Plain functions, no page state. */
(function (root) {
"use strict";
const STATES={AL:"Alabama",AK:"Alaska",AZ:"Arizona",AR:"Arkansas",CA:"California",CO:"Colorado",CT:"Connecticut",DE:"Delaware",FL:"Florida",GA:"Georgia",HI:"Hawaii",ID:"Idaho",IL:"Illinois",IN:"Indiana",IA:"Iowa",KS:"Kansas",KY:"Kentucky",LA:"Louisiana",ME:"Maine",MD:"Maryland",MA:"Massachusetts",MI:"Michigan",MN:"Minnesota",MS:"Mississippi",MO:"Missouri",MT:"Montana",NE:"Nebraska",NV:"Nevada",NH:"New Hampshire",NJ:"New Jersey",NM:"New Mexico",NY:"New York",NC:"North Carolina",ND:"North Dakota",OH:"Ohio",OK:"Oklahoma",OR:"Oregon",PA:"Pennsylvania",RI:"Rhode Island",SC:"South Carolina",SD:"South Dakota",TN:"Tennessee",TX:"Texas",UT:"Utah",VT:"Vermont",VA:"Virginia",WA:"Washington",WV:"West Virginia",WI:"Wisconsin",WY:"Wyoming",DC:"District of Columbia",PR:"Puerto Rico",GU:"Guam",VI:"U.S. Virgin Islands",AS:"American Samoa",MP:"Northern Mariana Islands"};
const STATE_BY_NAME=Object.fromEntries(Object.entries(STATES).map(([k,v])=>[v.toLowerCase(),k]));
/* "MN", "mn", "Minnesota" -> {st:"MN"}; "MN-5" -> {st:"MN",dist:"5"}; anything else -> null */
function stateQuery(q){
  const t=String(q||"").trim().toLowerCase().replace(/\.$/,"");
  let m=t.match(/^([a-z]{2})-(\d{1,2}|al)$/);if(m&&STATES[m[1].toUpperCase()])return{st:m[1].toUpperCase(),dist:m[2].toUpperCase()};
  if(/^[a-z]{2}$/.test(t)&&STATES[t.toUpperCase()])return{st:t.toUpperCase()};
  if(STATE_BY_NAME[t])return{st:STATE_BY_NAME[t]};
  return null;
}

/* readable bill names: the short title when there is one, else a shortened official title */
const AG=[["Bureau of Consumer Financial Protection","CFPB"],["Executive Office for Immigration Review","EOIR (immigration courts)"],["U.S. Citizenship and Immigration Services","USCIS"],["Citizenship and Immigration Services","USCIS"],["Immigration and Customs Enforcement","ICE"],["Customs and Border Protection","CBP"],["Centers for Medicare & Medicaid Services","CMS"],["Centers for Medicare and Medicaid Services","CMS"],["Environmental Protection Agency","EPA"],["Bureau of Land Management","BLM"],["Consumer Financial Protection Bureau","CFPB"],["Department of Energy","Energy Dept."],["Department of the Interior","Interior Dept."],["Department of Labor","Labor Dept."],["Department of Education","Education Dept."],["Department of Health and Human Services","HHS"],["Department of Agriculture","USDA"],["Department of Transportation","DOT"],["Department of the Treasury","Treasury"],["Department of Homeland Security","DHS"],["Department of Veterans Affairs","VA"],["Department of Commerce","Commerce Dept."],["Office of the Comptroller of the Currency","OCC"],["Federal Deposit Insurance Corporation","FDIC"],["Securities and Exchange Commission","SEC"],["Federal Communications Commission","FCC"],["Federal Energy Regulatory Commission","FERC"],["Internal Revenue Service","IRS"],["National Park Service","Park Service"],["Fish and Wildlife Service","Fish & Wildlife"],["National Oceanic and Atmospheric Administration","NOAA"],["Bureau of Ocean Energy Management","BOEM"],["Federal Trade Commission","FTC"],["Board of Governors of the Federal Reserve System","Federal Reserve"],["National Labor Relations Board","NLRB"],["Food and Drug Administration","FDA"],["Centers for Medicare & Medicaid Services","CMS"],["Office of Personnel Management","OPM"],["Federal Highway Administration","FHWA"],["National Highway Traffic Safety Administration","NHTSA"],["Department of Defense","Defense Dept."],["Department of Justice","Justice Dept."],["Department of Housing and Urban Development","HUD"],["Department of State","State Dept."]];
function abbr(s){let x=s.replace(/^the /i,"").replace(/^United States /,"").replace("Office of Energy Efficiency and Renewable Energy","Energy Dept.");for(const[a,b]of AG)x=x.split(a).join(b);
  x=x.replace(/ of the (Interior|Energy|Treasury|Labor|Commerce|Agriculture) Dept\.$/,"").replace(/,? (Interior|Energy|Labor|Commerce) Dept\.$/,"");
  x=x.replace(/ of the (HHS|USDA|DOT|DHS|HUD|VA|Treasury|[A-Z][a-z]+ Dept\.)$/,"");
  x=x.replace(/,? (Department of [A-Z][\w ]+|[A-Z][\w.]+ Dept\.)$/,m=>/^(,? )?(Energy|Interior|Labor|Commerce|Agriculture)/.test(m.replace(/^,? /,""))&&x.indexOf(m)>0?"":m);
  return x.replace(/ of (BLM|Interior Dept\.|Energy Dept\.)$/,"").replace(/^Energy Dept\., Energy Dept\.$/,"Energy Dept.")}
const GENERIC=/^(Energy Conservation Program|Endangered and Threatened Wildlife and Plants|Air Plan Approval|Air Quality State Implementation Plans)[:;]\s*/i;
function cut(s,n){s=s.trim();if(s.length<=n)return s;let c=s.slice(0,n);const i=c.lastIndexOf(" ");if(i>n*0.6)c=c.slice(0,i);return c.replace(/[\s,;:.\-–(]+$/,"")+"…"}
/* who a bill directs, and codes it amends, in plain words */
const SECY=[["the Secretary of Homeland Security","DHS"],["the Secretary of Agriculture","USDA"],["the Secretary of the Interior","Interior Dept."],["the Secretary of Veterans Affairs","VA"],["the Secretary of Defense","Defense Dept."],["the Secretary of Energy","Energy Dept."],["the Secretary of Health and Human Services","HHS"],["the Secretary of Transportation","DOT"],["the Secretary of the Treasury","Treasury"],["the Secretary of State","State Dept."],["the Secretary of Labor","Labor Dept."],["the Secretary of Commerce","Commerce Dept."],["the Secretary of Education","Education Dept."],["the Secretary of Housing and Urban Development","HUD"],["the Attorney General","Justice Dept."],["the Administrator of the Environmental Protection Agency","EPA"]];
function plainName(t){
  for(const[a,b]of SECY)t=t.split(a).join(b);
  for(const[a,b]of AG)t=t.split(a).join(b);
  t=t.replace(/\bthe (EPA|FERC|FCC|SEC|FTC|FDA|FDIC|IRS|NLRB|CFPB|OPM|NOAA|BLM|BOEM|CMS|FHWA|NHTSA|OCC|HHS|USDA|DOT|DHS|HUD)\b/g,"$1");
  return t.replace(/the Internal Revenue Code of 1986/g,"the tax code").replace(/title (\d+), United States Code/g,"title $1 of federal law");
}
/* the rule a resolution would overturn, without boilerplate */
function ruleSubject(x){
  x=x.replace(/^the /i,"").replace(/^["“”']+|["“”'.]+$/g,"");
  x=x.replace(/^withdrawal of the rule relat(?:ing|ed) to ["“”']?/i,"withdrawal of ");
  x=x.replace(GENERIC,"");
  x=x.replace(/^Medicare (?:and Medicaid )?Programs?[:;,]\s*/i,"").replace(/^Patient Protection and Affordable Care Act[:;,]\s*(?:HHS )?/i,"ACA ");
  x=x.replace(/^Energy Conservation Standards for /i,"efficiency standards for ");
  x=x.replace(/\s*(?:Record of Decision and )?Approved Resource Management Plan(?: Amendments?)?/i," land-use plan");
  if(x.length>50&&x.includes(";"))x=x.split(";")[0];
  return x.replace(/["“”']/g,"").trim();
}
function nameOf(t){
  t=decodeEnt(String(t||"")).trim().replace(/\s+/g," ");
  if(/^(A|An) (bill|joint resolution|concurrent resolution|executive resolution|resolution) to /i.test(t))t=t.replace(/^(A|An) [a-z ]*?(bill|resolution) to /i,"To ");
  else t=t.replace(/^(A|An) (joint resolution|concurrent resolution|executive resolution|resolution) ([a-z])/i,(m,a,b,c)=>c.toUpperCase());
  const wp=t.match(/^Directing the President,? pursuant to section 5\(c\) of the War Powers Resolution,? to remove (?:the )?United States Armed Forces from (.+?)\.?$/i);
  const wp2=t.match(/^To direct the removal of (?:the )?United States Armed Forces from (.+?)\.?$/i);
  const w=wp||wp2;
  if(w){const x=w[1].replace(/ that (?:have|has) not been authorized by Congress$/i,"").replace(/^hostilities within or against /i,"hostilities against ").replace(/the Islamic Republic of Iran/i,"Iran").replace(/the Bolivarian Republic of Venezuela/i,"Venezuela");return cut("War powers: remove U.S. forces from "+x,70)}
  const rl=t.match(/^Providing for consideration of (?:the )?(?:bill|joint resolution|resolution)s? \(([^)]+)\)/i);
  if(rl)return cut("Rule for debating "+rl[1]+(/and (?:the )?(?:bill|joint resolution)/i.test(t)?" and others":""),70);
  const fms=t.match(/^Providing for congressional disapproval of the proposed (?:foreign military sale|direct commercial sale|export|sale)s? to (?:the )?(?:Government of )?(.+?) of .+$/i);
  if(fms)return cut("Block proposed arms sale to "+fms[1],70);
  const fex=t.match(/^Providing for congressional disapproval of the proposed export of .+? to (?:the )?(.+?)\.?$/i);
  if(fex)return cut("Block proposed arms export to "+fex[1],70);
  const tar=t.match(/^Terminating the national emergency declared to impose (?:duties on articles imported from|tariffs on(?: imports from)?) (?:the )?(.+?)\.?$/i);
  if(tar)return cut("End the national emergency behind tariffs on "+tar[1],70);
  if(/^Terminating the national emergency declared to impose global tariffs/i.test(t))return"End the national emergency behind global tariffs";
  const ne=t.match(/^Terminating (the national emergency .+?)\.?$/i);
  if(ne)return cut("End "+ne[1],70);
  const m=t.match(/^Providing (?:for )?congressional disapproval under chapter 8 of title 5, United States Code, of the rule (?:submitted|issued|published) by (.+?) relat(?:ing|ed) to (.+?)\.?$/i);
  if(m){const head="Overturn "+cut(abbr(m[1]),28)+" rule: ";return head+cut(ruleSubject(m[2]),Math.max(24,78-head.length))}
  const mt=t.match(/^Providing (?:for )?congressional disapproval under chapter 8 of title 5, United States Code, of (?:a|the) rule (?:submitted|issued|published) by (.+)$/i);
  if(mt){const ag=abbr(mt[1]).replace(/,? of the Department\b.*$/i,"").replace(/,? Department of [^,]*$/i,"").trim();return"Overturn "+cut(ag,40)+" rule"}
  if(/^Providing (?:for )?congressional disapproval under chapter 8/i.test(t))return"Overturn an agency rule";
  const c=t.match(/^Proposing an amendment to the Constitution of the United States,? (.+?)\.?$/i);
  if(c){const x=c[1].replace(/^relat(?:ive|ing) to /i,"on ").replace(/ of the United States/g,"");return cut("Constitutional amendment "+x,70)}
  const dc=t.match(/^Disapproving the action of the District of Columbia Council in approving (?:the )?(.+?)\.?$/i);
  if(dc)return cut("Block D.C. law: "+dc[1],70);
  const r=t.match(/^Relating to a national emergency declared by the President on (.+?)\.?$/i);
  if(r)return cut("End national emergency declared "+r[1],70);
  const ap=t.match(/^(.+;.+) Appropriations Act, (\d{4})\.?$/i);
  if(ap){const parts=ap[1].split(/;\s*(?:and\s+)?/).map(x=>x.replace(/,? and Related Agencies/gi,"").replace(/ Development\b/g,"").replace(/ and Environment\b/g,"").trim());return cut(`${ap[2]} funding: ${parts.join(" / ")}`,80)}
  t=t.replace(/^(A|An) (bill|joint resolution|concurrent resolution|resolution) to /i,"To ").replace(/,? and for other purposes\.?$/i,"").replace(/\.$/,"");
  if(/^To [a-z]/.test(t)){t=plainName(t);t=t.charAt(3).toUpperCase()+t.slice(4)}  // descriptions only; short titles stay as Congress named them
  return cut(t,70);
}
function decodeEnt(s){return s.replace(/&#(\d+);/g,(m,n)=>String.fromCharCode(+n)).replace(/&amp;/g,"&").replace(/&quot;/g,'"').replace(/&#39;|&apos;/g,"'")}
const MTYPE={HR:["H.R.","house-bill"],S:["S.","senate-bill"],HRES:["H.Res.","house-resolution"],SRES:["S.Res.","senate-resolution"],HJRES:["H.J.Res.","house-joint-resolution"],SJRES:["S.J.Res.","senate-joint-resolution"],HCONRES:["H.Con.Res.","house-concurrent-resolution"],SCONRES:["S.Con.Res.","senate-concurrent-resolution"],PN:["PN","nomination"]};
function measureInfo(raw,congress){
  const m=String(raw||"").toUpperCase().replace(/\./g,"").match(/^\s*([A-Z]+)\s*0*(\d+)/);if(!m||!MTYPE[m[1]])return null;
  const [label,path]=MTYPE[m[1]];const c=congress||119;
  return{type:m[1],num:m[2],label:`${label} ${m[2]}`,url:path==="nomination"?`https://www.congress.gov/nomination/${c}th-congress/${m[2]}`:`https://www.congress.gov/bill/${c}th-congress/${path}/${m[2]}`};
}
/* "Angela Veronica Colmenero, of Texas, to be United States District Judge for ..." */
function nomName(t){t=decodeEnt(plain(t));const m=t.match(/^(.+?), of (.+?), to be (.+?)(?:, vice .*)?$/i);if(!m)return cut(t,80);return cut(`${m[1]} to be ${m[3].replace(/United States/g,"U.S.")}`,80)}
const plain=s=>String(s||"").replace(/<[^>]*>/g,"").replace(/\s+/g," ").trim();
const numKey=s=>String(s||"").replace(/[^a-z0-9]/gi,"").toLowerCase();

const api = { SECY, plainName, ruleSubject, STATES, STATE_BY_NAME, stateQuery, AG, abbr, GENERIC, cut, nameOf, decodeEnt, MTYPE, measureInfo, nomName, plain, numKey };
if (typeof module !== "undefined" && module.exports) module.exports = api;
else Object.assign(root, api);
})(typeof window !== "undefined" ? window : globalThis);
