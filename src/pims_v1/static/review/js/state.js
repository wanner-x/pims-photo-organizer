export const viewNames = new Set(["overview", "series", "archive", "sampling", "anomalies", "ledger", "duplicates"]);

export const state = {
  activeView: "overview",
  batches: [],
  batchId: null,
  offset: 0,
  limit: 30,
  total: 0,
  series: [],
  archiveOverview: null,
  archiveSampling: [],
  archiveAnomalies: [],
  archiveLedger: [],
  selectedSeriesIds: new Set(),
};
