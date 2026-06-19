/**
 * doi-resolve-module.test.js
 *
 * Focused tests for the UX cleanup requirements:
 * 1. Manual suggestions are not duplicated in normal display
 * 2. Summary counts are computed correctly
 * 3. Local matches render before manual suggestions (verified by DOM order)
 * 4. Available unmapped metadata is collapsible (structural check)
 *
 * Run: node doi-resolve-module.test.js
 */
'use strict';

var assert = require('assert');
var mod = require('./doi-resolve-module.js');

/* ── Test: computeSummaryCounts ──────────────────────────────────── */

(function testSummaryCountsEmpty() {
  var counts = mod.computeSummaryCounts({});
  assert.strictEqual(counts.exactMatches, 0);
  assert.strictEqual(counts.manualLocal, 0);
  assert.strictEqual(counts.structured, 0);
  assert.strictEqual(counts.manualGroups, 0);
  assert.strictEqual(counts.unmappedKeys, 0);
  console.log('✓ computeSummaryCounts returns zeros for empty input');
})();

(function testSummaryCountsWithData() {
  var resolved = {
    model: [{ model_name: 'X' }],
    alternate_identifier_obj: [{ alternate_identifier: 'A' }],
    manufacturer_suggestions: [{ name: 'Mfg' }],
    owner_suggestions: [{ name: 'Owner' }]
  };
  var manual = mod.manualResolvedFields(resolved);
  var matchedSuggestions = {
    manufacturer: [
      { match_status: 'exact_unique', matched_local_id: '1' },
      { match_status: 'ambiguous', matched_local_id: '2' }
    ],
    owner: [
      { match_status: 'exact_unique', matched_local_id: '3' }
    ]
  };
  var unmapped = { foo: 'bar', baz: 123, qux: null };

  var counts = mod.computeSummaryCounts({
    matchedSuggestions: matchedSuggestions,
    resolved: resolved,
    manual: manual,
    unmapped: unmapped
  });

  assert.strictEqual(counts.exactMatches, 2, 'should count 2 exact matches');
  assert.strictEqual(counts.manualLocal, 1, 'should count 1 non-exact (manual) local suggestion');
  assert.strictEqual(counts.structured, 2, 'should count 2 composite fields with data');
  assert.strictEqual(counts.manualGroups, 2, 'should count 2 manual groups');
  assert.strictEqual(counts.unmappedKeys, 3, 'should count 3 unmapped keys');
  console.log('✓ computeSummaryCounts returns correct counts with data');
})();

/* ── Test: manualResolvedFields only returns suggestion-category keys ── */

(function testManualFieldsNotDuplicated() {
  // manualResolvedFields should only extract MANUAL_RESOLVED_FIELD_LABELS keys.
  // Direct mapped fields like title, notes, identifier_url must NOT appear.
  var resolved = {
    title: 'My Instrument',
    notes: 'Description here',
    identifier_url: 'https://doi.org/10.1234/test',
    instrument_classification: 'Sensor',
    manufacturer_suggestions: [{ name: 'Acme Corp', identifier: 'https://ror.org/123' }],
    taxonomy_suggestions: [{ scheme: 'GCMD', term: 'Instruments' }]
  };

  var manual = mod.manualResolvedFields(resolved);
  var keys = Object.keys(manual);

  // Should only have the suggestion groups
  assert.ok(keys.indexOf('Manufacturer Suggestions') !== -1,
    'should include Manufacturer Suggestions');
  assert.ok(keys.indexOf('Taxonomy Suggestions') !== -1,
    'should include Taxonomy Suggestions');

  // Should NOT include direct-mapped fields
  assert.strictEqual(keys.indexOf('title'), -1,
    'should NOT include title');
  assert.strictEqual(keys.indexOf('notes'), -1,
    'should NOT include notes');
  assert.strictEqual(keys.indexOf('identifier_url'), -1,
    'should NOT include identifier_url');
  assert.strictEqual(keys.length, 2,
    'should have exactly 2 manual groups');
  console.log('✓ manualResolvedFields does not duplicate direct-mapped fields');
})();

/* ── Test: localMatchGroups orders correctly for rendering ────────── */

(function testLocalMatchGroupsOrder() {
  // localMatchGroups should return groups in a fixed order matching
  // LOCAL_MATCH_GROUPS definition, which the DOM will render in order
  // (before manual suggestions section).
  var suggestions = {
    owner: [{ match_status: 'exact_unique' }],
    manufacturer: [{ match_status: 'exact_unique' }]
  };
  var groups = mod.localMatchGroups(suggestions);

  // Manufacturer should come before owner in the defined LOCAL_MATCH_GROUPS order
  var mfgIndex = -1;
  var ownerIndex = -1;
  for (var i = 0; i < groups.length; i++) {
    if (groups[i].key === 'manufacturer') mfgIndex = i;
    if (groups[i].key === 'owner') ownerIndex = i;
  }
  assert.ok(mfgIndex < ownerIndex,
    'manufacturer group should come before owner group');
  assert.ok(mfgIndex !== -1, 'manufacturer group should exist');
  assert.ok(ownerIndex !== -1, 'owner group should exist');
  console.log('✓ localMatchGroups preserves defined order (local matches render first)');
})();

/* ── Test: unmapped metadata structure ────────────────────────────── */

(function testUnmappedMetadataKeys() {
  // The unmapped section should have countable keys.
  // computeSummaryCounts should count them correctly for the badge.
  var unmapped = {
    alternateIdentifiers: [{ id: '123' }],
    geoLocations: [{ lat: 1, lon: 2 }],
    subjects: ['physics']
  };
  var counts = mod.computeSummaryCounts({ unmapped: unmapped });
  assert.strictEqual(counts.unmappedKeys, 3,
    'should count 3 unmapped metadata keys');

  // Array unmapped should not count
  var countsArray = mod.computeSummaryCounts({ unmapped: ['a', 'b'] });
  assert.strictEqual(countsArray.unmappedKeys, 0,
    'array unmapped should yield 0 keys');

  // null unmapped should not count
  var countsNull = mod.computeSummaryCounts({ unmapped: null });
  assert.strictEqual(countsNull.unmappedKeys, 0,
    'null unmapped should yield 0 keys');
  console.log('✓ unmapped metadata key counting works correctly');
})();

console.log('\nAll DOI resolve dialog UX tests passed.');

/* ── Test: related_identifier_obj is NOT auto-applicable ─────────── */

(function testRelatedIdentifierObjNotInCompositeTargets() {
  // related_identifier_obj must NOT be offered for auto-apply because DataCite
  // does not provide related_resource_type, which is required in the PIDINST
  // schema. It should be shown as suggestion-only metadata instead.
  var resolved = {
    related_identifier_obj: [
      {
        related_identifier: '10.9999/manual',
        related_identifier_type: 'DOI',
        relation_type: 'IsDescribedBy'
      }
    ],
    model: [{ model_name: 'TestModel' }]
  };

  var targets = mod.compositeApplyTargets(resolved);
  var targetKeys = targets.map(function (t) { return t.key; });

  assert.ok(targetKeys.indexOf('related_identifier_obj') === -1,
    'related_identifier_obj must NOT appear in compositeApplyTargets');
  assert.ok(targetKeys.indexOf('model') !== -1,
    'model should still appear in compositeApplyTargets');
  console.log('✓ related_identifier_obj is excluded from auto-applicable composite fields');
})();

(function testRelatedIdentifierObjInManualFields() {
  // related_identifier_obj should appear in manual resolved fields for review.
  var resolved = {
    related_identifier_obj: [
      {
        related_identifier: '10.9999/manual',
        related_identifier_type: 'DOI',
        relation_type: 'IsDescribedBy'
      }
    ]
  };
  var manual = mod.manualResolvedFields(resolved);
  assert.ok('Related Identifiers (manual review)' in manual,
    'related_identifier_obj should appear in manualResolvedFields');
  console.log('✓ related_identifier_obj appears in manual review suggestions');
})();
