// Classifies contract changes for the browser catalog; must agree with the Python CLI (spec/cases.json).

const WIDENING = new Set(["integer>number"]);
const UNIT_SECONDS = { m: 60, min: 60, h: 3600, d: 86400 };

/** Normalised view of a decoded (already validated) contract document. */
export function normalize(doc) {
  const owner = (doc.team ?? []).find((m) => m.role === "owner")?.username ?? "";
  const sla = (doc.slaProperties ?? []).find((s) => s.property === "freshness");
  const datasets = new Map();
  for (const ds of doc.schema) {
    const fields = new Map();
    for (const p of ds.properties) {
      fields.set(p.name, {
        type: p.logicalType,
        required: p.required === true,
        primaryKey: p.primaryKey === true,
        description: p.description ?? "",
        allowed: p.allowedValues ?? null,
      });
    }
    datasets.set(ds.name, fields);
  }
  return {
    id: doc.id,
    owner,
    description: doc.description ?? "",
    freshness: sla ? sla.value * UNIT_SECONDS[sla.unit] : null,
    datasets,
  };
}

/** Every change from oldDoc to newDoc as { kind, path, breaking, detail }, in a stable order. */
export function diff(oldDoc, newDoc) {
  const a = normalize(oldDoc);
  const b = normalize(newDoc);
  if (a.id !== b.id) throw new Error(`different contracts: ${a.id} vs ${b.id}`);
  const out = [];
  const add = (kind, path, breaking, detail) => out.push({ kind, path, breaking, detail });
  if (a.owner !== b.owner) add("owner-changed", b.id, false, `${a.owner} -> ${b.owner}`);
  if (a.description !== b.description) add("description-changed", b.id, false, "contract description edited");
  if (a.freshness !== b.freshness) {
    if (a.freshness === null) add("freshness-added", b.id, false, `data at most ${b.freshness}s old`);
    else if (b.freshness === null) add("freshness-removed", b.id, true, "no freshness guarantee any more");
    else if (b.freshness > a.freshness) add("freshness-loosened", b.id, true, `${a.freshness}s -> ${b.freshness}s`);
    else add("freshness-tightened", b.id, false, `${a.freshness}s -> ${b.freshness}s`);
  }
  for (const [name, fields] of a.datasets) {
    if (!b.datasets.has(name)) add("dataset-removed", name, true, "consumers of this table lose it");
    else datasetChanges(name, fields, b.datasets.get(name), add);
  }
  for (const name of b.datasets.keys()) if (!a.datasets.has(name)) add("dataset-added", name, false, "new table");
  return out;
}

/** Changes inside one table. */
function datasetChanges(name, oldFields, newFields, add) {
  const pk = (fields) => [...fields].filter(([, f]) => f.primaryKey).map(([n]) => n);
  const oldPk = pk(oldFields);
  const newPk = pk(newFields);
  if (JSON.stringify(oldPk) !== JSON.stringify(newPk)) add("primary-key-changed", name, true, `${oldPk} -> ${newPk}`);
  for (const [field, f] of oldFields) {
    const path = `${name}.${field}`;
    if (!newFields.has(field)) add("field-removed", path, true, "consumers selecting it will fail");
    else fieldChanges(path, f, newFields.get(field), add);
  }
  for (const [field, f] of newFields) {
    if (!oldFields.has(field)) add("field-added", `${name}.${field}`, false, `new ${f.required ? "required" : "optional"} ${f.type}`);
  }
}

/** Changes to one column. */
function fieldChanges(path, a, b, add) {
  if (a.type !== b.type) {
    const widened = WIDENING.has(`${a.type}>${b.type}`);
    add(widened ? "type-widened" : "type-changed", path, !widened, `${a.type} -> ${b.type}`);
  }
  if (a.required && !b.required) add("became-optional", path, true, "consumers may now receive nulls");
  else if (b.required && !a.required) add("became-required", path, false, "nulls no longer allowed");
  if (a.allowed !== null && b.allowed === null) add("allowed-values-removed", path, true, "any value may now appear");
  else if (a.allowed === null && b.allowed !== null) add("allowed-values-added", path, false, `restricted to ${b.allowed}`);
  else if (a.allowed !== null && b.allowed !== null) {
    const added = b.allowed.filter((v) => !a.allowed.includes(v));
    const dropped = a.allowed.filter((v) => !b.allowed.includes(v));
    if (added.length) add("allowed-values-extended", path, true, `new values ${added}`);
    if (dropped.length) add("allowed-values-narrowed", path, false, `values no longer used ${dropped}`);
  }
  if (a.description !== b.description) add("description-changed", path, false, "field description edited");
}
