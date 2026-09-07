// Plain-assert Node tests for app-logic.js. Run: node test_app_logic.js  -> prints "ok"
const L = require("./app-logic.js");
const assert = require("assert");

const campaigns = [{id:"a",name:"Amp",targetType:"organization",goal:"g",
  states:[{key:"replied",label:"Replied",kind:"active"},
          {key:"published",label:"Published",kind:"won"},
          {key:"passed",label:"Passed",kind:"lost"}]}];
const orgs = [{id:"a:bookviral",name:"BookViral",sector:"Blog",region:null,url:null,campaignId:"a"}];
const leads = [
  {id:"a:bookviral",orgId:"a:bookviral",campaignId:"a",name:"James",emails:[],state:"replied",
   strength:"stretch",followUpDate:"2020-01-01",waiting:"them",facts:{paidStatus:"paid"}},
  {id:"a:other",orgId:"a:bookviral",campaignId:"a",name:"Other",emails:[],state:"passed",
   strength:"medium",followUpDate:null,waiting:"them",facts:{paidStatus:"free"}},
];

const m = L.buildModel(campaigns, orgs, leads, {});
assert.strictEqual(m.leadsByCampaign["a"].length, 2);
assert.strictEqual(m.leadsByOrg["a:bookviral"].length, 2);
assert.strictEqual(L.stateKind(campaigns[0], "published"), "won");
assert.strictEqual(L.stateKind(campaigns[0], "nope"), "unknown");

const roll = L.orgRollup(orgs[0], m.leadsByOrg, m.campaignsById);
assert.strictEqual(roll.leadCount, 2);
assert.strictEqual(roll.counts.lost, 1);
assert.strictEqual(roll.counts.active, 1);
assert.strictEqual(roll.alive, true); // one lead is "replied" (active)

assert.strictEqual(L.leadDue(leads[0], new Date("2026-01-01")), true);  // past followUp
assert.strictEqual(L.leadDue(leads[1], new Date("2026-01-01")), false); // no followUp date

const f = L.campaignFunnel(campaigns[0], leads);
assert.strictEqual(f.total, 2);
assert.strictEqual(f.byKind.lost, 1);
assert.strictEqual(f.byKind.active, 1);
assert.strictEqual(f.byState.replied, 1);
assert.strictEqual(f.pctWon, 0);

// empty campaign funnel: no divide-by-zero
const e = L.campaignFunnel(campaigns[0], []);
assert.strictEqual(e.total, 0);
assert.strictEqual(e.pctWon, 0);

// bot flag is stale once a non-bot Log entry postdates the inbound
const cm = [{key:"a:acme",via:"bot",ts:"2026-09-03T12:00:00Z"},{key:"a:acme",via:"api",ts:"2026-09-05T09:00:00Z"}];
assert.strictEqual(L.actedSince(cm, "a:acme", "2026-09-03T12:34:05Z"), true);
assert.strictEqual(L.actedSince(cm, "a:acme", "2026-09-06T00:00:00Z"), false);
assert.strictEqual(L.actedSince(cm, "a:other", "2026-09-03T12:34:05Z"), false);

// Won/Drop on a campaign with no lost state: propose a new "passed" state; reuse an existing one otherwise
const noLost = {id:"f", states:[{key:"prospect",kind:"active"},{key:"won",kind:"won"}]};
assert.deepStrictEqual(L.closeState(noLost, "lost"), {state:{key:"passed",label:"Passed",kind:"lost"}, isNew:true});
assert.deepStrictEqual(L.closeState(noLost, "won"), {state:{key:"won",kind:"won"}, isNew:false});
assert.strictEqual(L.closeState({states:[{key:"passed",kind:"active"}]}, "lost").state.key, "passed-closed");
// with a second won-state ("referred"), the Won button still resolves to the canonical "won"
const twoWon = {states:[{key:"won",kind:"won"},{key:"referred",kind:"won"},{key:"passed",kind:"lost"}]};
assert.strictEqual(L.closeState(twoWon, "won").state.key, "won");
assert.strictEqual(L.closeState(twoWon, "lost").state.key, "passed");
// a lead already in a won-kind state stays there: Won must not fall back to another won state
const multiWon = {states:[{key:"scheduled",kind:"won"},{key:"published",kind:"won"},{key:"passed",kind:"lost"}]};
assert.deepStrictEqual(L.closeState(multiWon, "won", "published"), {state:{key:"published",kind:"won"}, isNew:false, already:true});
assert.strictEqual(L.closeState(multiWon, "won", "passed").state.key, "scheduled");

// meetingMismatch: true only when followUpDate != meeting date (catches reschedules / missing date)
assert.strictEqual(L.meetingMismatch({followUpDate:"2026-09-23"},{start:"2026-09-23T10:30:00+03:00"}), false);
assert.strictEqual(L.meetingMismatch({followUpDate:"2026-09-20"},{start:"2026-09-23T10:30:00+03:00"}), true);
assert.strictEqual(L.meetingMismatch({followUpDate:null},{start:"2027-01-27T09:00:00+02:00"}), true);

// funnelStages: furthest stage reached; evidence beats labels; entryStage floors imported campaigns
const fcamp = {id:"x", states:[{key:"prospect",kind:"active"},{key:"contacted",kind:"active"},{key:"followup",kind:"active"},
  {key:"bounce",kind:"lost"},{key:"declined",kind:"lost"},{key:"won",kind:"won"}]};
const fleads = [{id:"x:p",state:"prospect"},{id:"x:c",state:"contacted"},{id:"x:b",state:"bounce"},
  {id:"x:f",state:"followup"},{id:"x:d",state:"declined"},{id:"x:w",state:"won"}];
const ff = L.funnelStages(fcamp, fleads, {"x:f":[{direction:"received"}]}, {});
assert.deepStrictEqual(ff.reached, [6,5,3,1]);  // followup with a reply on record is engaged
assert.deepStrictEqual(ff.lostAt, [0,1,1,0]);   // bounce drops at contacted, declined at engaged
const fo = L.funnelStages(fcamp, [{id:"x:o",state:"followup"}], {}, {"x:o":{lastInbound:"2026-09-01T00:00:00Z"}});
assert.deepStrictEqual(fo.reached, [1,1,1,0]);  // bot-observed inbound counts as a reply
const fa = L.funnelStages({id:"a",entryStage:"engaged",states:[{key:"passed",kind:"lost"}]}, [{id:"a:1",state:"passed"}], {}, {});
assert.deepStrictEqual(fa.reached, [1,1,1,0]); assert.deepStrictEqual(fa.lostAt, [0,0,1,0]);

console.log("ok");
