import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { diff } from "../src/index.js";

const { cases } = JSON.parse(readFileSync(new URL("../../spec/cases.json", import.meta.url), "utf8"));

for (const c of cases) {
  test(`shared case: ${c.name}`, () => {
    const got = diff(c.old, c.new).map((ch) => [ch.kind, ch.path, ch.breaking]);
    assert.deepEqual(got, c.expect);
  });
}

test("different contracts cannot be compared", () => {
  assert.throws(() => diff(cases[0].old, { ...cases[0].new, id: "payments" }), /different contracts/);
});
