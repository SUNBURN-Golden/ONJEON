// Run by build_check.sh against the compiled public entry point.
const assert = require("node:assert/strict");
const { readdirSync, readFileSync } = require("node:fs");
const { join } = require("node:path");
const { test } = require("node:test");
const { runInNewContext } = require("node:vm");

const [, , entryPoint, fixtures, vocabulary] = process.argv;
const contracts = require(entryPoint);
const { parseAssertion, parsePlanView, parsePremiumObservation, parseScenarioResult } = contracts;

function readFixture(name) {
  return JSON.parse(readFileSync(join(fixtures, `${name}.fixture.json`), "utf8"));
}

function rejects(parse, input, message) {
  assert.throws(() => parse(input), { name: "TypeError", message });
}

for (const file of readdirSync(fixtures).filter((file) => file.endsWith(".fixture.json")).sort()) {
  test(`decode ${file}`, () => {
    const type = file.split(".")[0];
    const input = JSON.parse(readFileSync(join(fixtures, file), "utf8"));
    assert.deepStrictEqual(contracts[`parse${type}`](input), input);
  });
}

test("all vocabulary metadata matches the registry and cannot change wire decoding", () => {
  const { axes } = JSON.parse(readFileSync(vocabulary, "utf8"));
  for (const axis of axes) {
    const name = axis.id.split("_").map(word => word[0].toUpperCase() + word.slice(1)).join("");
    const metadata = contracts[`${name}Metadata`];
    const parse = contracts[`parse${name}`];
    assert.deepStrictEqual(Object.keys(metadata), axis.values.map(value => value.code), axis.id);
    const hasMapsTo = axis.values.some(value => "maps_to" in value);
    for (const value of axis.values) {
      const label = `${axis.id}.${value.code}`;
      const expected = { screenKo: value.screen_ko, deprecatedAliases: value.deprecated_aliases };
      if (hasMapsTo) expected.mapsTo = value.maps_to ?? null;
      if (axis.id === "diff_type") expected.group = value.group;
      assert.deepStrictEqual(metadata[value.code], expected, label);
      assert.equal(parse(value.code), value.code, label);
      for (const alias of value.deprecated_aliases) {
        assert.throws(() => parse(alias), /unknown /, `${label} accepted ${alias}`);
      }
    }
  }
});

test("two-plan comparison reads the screen text from the change group", () => {
  const { DiffGroupMetadata, DiffTypeMetadata } = contracts;
  const plan = parsePlanView(readFixture("PlanView"));
  const diffGroup = plan.diff.groups[0];
  const diff = DiffTypeMetadata[diffGroup.items[0].diff_type];
  assert.equal(diff.screenKo, null);
  assert.equal(diff.group, diffGroup.group);
  assert.equal(DiffGroupMetadata[diff.group].screenKo, "줄어드는 것");
});

test("decode JSON from another realm and validate its nested enums", () => {
  const body = readFileSync(join(fixtures, "Assertion.relation.fixture.json"), "utf8");
  const input = runInNewContext("JSON.parse(body)", { body });
  assert.deepStrictEqual(parseAssertion(input), JSON.parse(body));

  input.evidence[0].role = "future_role";
  rejects(parseAssertion, input, "Assertion.evidence[0].role: unknown vocabulary value");
});

test("reject unknown enums at a document field and inside nested objects and arrays", () => {
  const assertion = readFixture("Assertion.relation");
  rejects(parseAssertion, { ...assertion, criticality: "c9" },
    "Assertion.criticality: unknown vocabulary value");
  assertion.evidence[0].role = "future_role";
  rejects(parseAssertion, assertion, "Assertion.evidence[0].role: unknown vocabulary value");
  const scenario = readFixture("ScenarioResult.evaluated");
  scenario.evaluation.eligibility = "future_eligibility";
  rejects(parseScenarioResult, scenario, "ScenarioResult.evaluation.eligibility: unknown vocabulary value");
});

test("check present optional enum fields", () => {
  const assertion = readFixture("Assertion.value");
  assertion.value.amount_form = "future_amount_form";
  rejects(parseAssertion, assertion, "Assertion.value.amount_form: unknown vocabulary value");
});

test("require keys even for nullable fields and preserve explicit null where allowed", () => {
  const scenario = readFixture("ScenarioResult.evaluated");
  assert.equal(parseScenarioResult(scenario).evaluation.release_id, null);
  delete scenario.evaluation.release_id;
  rejects(parseScenarioResult, scenario, "ScenarioResult.evaluation.release_id: missing required field");
  const assertion = readFixture("Assertion.relation");
  assertion.object = null;
  rejects(parseAssertion, assertion, "Assertion.object: expected a string");
});

test("reject missing keys, wrong scalar types and wrong container shapes", () => {
  const assertion = readFixture("Assertion.relation");
  const { evidence, ...missingEvidence } = assertion;
  rejects(parseAssertion, missingEvidence, "Assertion.evidence: missing required field");
  rejects(parseAssertion, { ...assertion, evidence: evidence[0] }, "Assertion.evidence: expected an array");
  rejects(parseAssertion, [], "Assertion: expected an object");
  rejects(parseAssertion, Object.create(assertion), "Assertion: expected a plain object");
  const customPrototype = Object.assign(Object.create(null), { constructor: Object });
  rejects(parseAssertion, Object.assign(Object.create(customPrototype), assertion),
    "Assertion: expected a plain object");
  const foreignInstance = runInNewContext("Object.assign(new (class {})(), assertion)", { assertion });
  rejects(parseAssertion, foreignInstance, "Assertion: expected a plain object");

  const premium = readFixture("PremiumObservation.full");
  rejects(parsePremiumObservation, { ...premium, raw_amount: 1.5 },
    "PremiumObservation.raw_amount: expected an integer");
  rejects(parsePremiumObservation, { ...premium, comparison_eligible: "false" },
    "PremiumObservation.comparison_eligible: expected a boolean");
  rejects(parsePremiumObservation, { ...premium, conditions: [] },
    "PremiumObservation.conditions: expected an object");
  rejects(parsePremiumObservation, { ...premium, conditions: { age: 40 } },
    'PremiumObservation.conditions["age"]: expected a string');

  const plan = readFixture("PlanView");
  plan.budget.value_man = Infinity;
  rejects(parsePlanView, plan, "PlanView.budget.value_man: expected a finite number");
});

test("ignore unknown struct fields and preserve open map keys", () => {
  const assertion = readFixture("Assertion.relation");
  const input = {
    ...assertion,
    future_field: "future_value",
    evidence: [{ ...assertion.evidence[0], future_field: "future_value" }],
  };
  assert.deepStrictEqual(parseAssertion(input), assertion);
  assert.equal(input.evidence[0].future_field, "future_value");
  assert.equal(Object.hasOwn(parseAssertion(input), "value"), false);

  const premium = readFixture("PremiumObservation.full");
  premium.conditions = JSON.parse('{"age":"40","__proto__":"dimension"}');
  assert.deepStrictEqual(parsePremiumObservation(premium), premium);
});
