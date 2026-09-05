// Plain-assert Node tests for app-logic.js. Run: node test_app_logic.js  -> prints "ok"
const L = require("./app-logic.js");
const assert = require("assert");

const campaigns = [{id:"a",name:"Amp",targetType:"organization",goal:"g",
  states:[{key:"replied",label:"Replied",kind:"active"},
          {key:"published",label:"Published",kind:"won"},
          {key:"passed",label:"Passed",kind:"lost"}]}];
const orgs = [{id:"a:acme",name:"Acme",sector:"Blog",region:null,url:null,campaignId:"a"}];
const leads = [
  {id:"a:acme",orgId:"a:acme",campaignId:"a",name:"Jane Doe",emails:[],state:"replied",
   strength:"stretch",followUpDate:"2020-01-01",waiting:"them",facts:{paidStatus:"paid"}},
  {id:"a:other",orgId:"a:acme",campaignId:"a",name:"Other",emails:[],state:"passed",
   strength:"medium",followUpDate:null,waiting:"them",facts:{paidStatus:"free"}},
];

const m = L.buildModel(campaigns, orgs, leads, {});
assert.strictEqual(m.leadsByCampaign["a"].length, 2);
assert.strictEqual(m.leadsByOrg["a:acme"].length, 2);
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

console.log("ok");
