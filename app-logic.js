// app-logic.js — pure, DOM-free helpers for app.html. Loaded by the page (<script>)
// and by Node tests (require). No fetch, no DOM, no globals beyond the export shim.
(function (root) {
  function buildModel(campaigns, orgs, leads, trail) {
    const campaignsById = {}, orgsById = {}, leadsById = {};
    const leadsByOrg = {}, leadsByCampaign = {};
    campaigns.forEach(c => campaignsById[c.id] = c);
    orgs.forEach(o => orgsById[o.id] = o);
    leads.forEach(l => {
      leadsById[l.id] = l;
      (leadsByOrg[l.orgId] = leadsByOrg[l.orgId] || []).push(l);
      (leadsByCampaign[l.campaignId] = leadsByCampaign[l.campaignId] || []).push(l);
    });
    return { campaignsById, orgsById, leadsById, leadsByOrg, leadsByCampaign,
             trailByLead: trail || {} };
  }

  function stateKind(campaign, stateKey) {
    if (!campaign) return "unknown";
    const s = (campaign.states || []).find(s => s.key === stateKey);
    return s ? s.kind : "unknown";
  }

  function orgRollup(org, leadsByOrg, campaignsById) {
    const ls = leadsByOrg[org.id] || [];
    const counts = { active: 0, won: 0, lost: 0 };
    ls.forEach(l => {
      const k = stateKind(campaignsById[l.campaignId], l.state);
      if (counts[k] !== undefined) counts[k]++;
    });
    return {
      alive: ls.some(l => stateKind(campaignsById[l.campaignId], l.state) !== "lost"),
      counts, leadCount: ls.length
    };
  }

  // Bare date check: followUpDate present and due. The Today view pairs this with an
  // active-kind check so lost/won rows don't resurface.
  function leadDue(lead, today) {
    today = today || new Date();
    if (!lead.followUpDate) return false;
    return new Date(lead.followUpDate) <= today;
  }

  function campaignFunnel(campaign, leads) {
    const byKind = { active: 0, won: 0, lost: 0 }, byState = {};
    leads.forEach(l => {
      const k = stateKind(campaign, l.state);
      if (byKind[k] !== undefined) byKind[k]++;
      byState[l.state] = (byState[l.state] || 0) + 1;
    });
    const total = leads.length;
    return { total, byKind, byState, pctWon: total ? Math.round(100 * byKind.won / total) : 0 };
  }

  // A bot flag (needsAction) is stale once the user has acted on the lead after the
  // inbound that raised it: any non-bot Log entry newer than `since` counts as acting.
  function actedSince(comments, leadId, since) {
    return (comments || []).some(x => x.key === leadId && x.via !== "bot" && String(x.ts || "") > String(since || ""));
  }

  const api = { buildModel, stateKind, orgRollup, leadDue, campaignFunnel, actedSince };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.AppLogic = api;
})(typeof window !== "undefined" ? window : globalThis);
