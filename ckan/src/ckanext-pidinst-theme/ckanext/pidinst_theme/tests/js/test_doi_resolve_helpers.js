'use strict';

var assert = require('assert');
var helpers = require('../../assets/js/doi-resolve-module.js');

assert.strictEqual(helpers.defaultApplyState(''), true);
assert.strictEqual(helpers.defaultApplyState('   '), true);
assert.strictEqual(helpers.defaultApplyState('existing'), false);
assert.strictEqual(helpers.defaultApplyState('Geophysics'), false);
assert.strictEqual(helpers.hasDisplayableMetadata({}), false);
assert.strictEqual(helpers.hasDisplayableMetadata({ nested: ['value'] }), true);
assert.strictEqual(
  helpers.formatJsonForDisplay({
    title: ['Instrument'],
    nested: { rights: [{ URL: 'https://example.test/license' }] }
  }),
  '{\n' +
    '  "title": [\n' +
    '    "Instrument"\n' +
    '  ],\n' +
    '  "nested": {\n' +
    '    "rights": [\n' +
    '      {\n' +
    '        "URL": "https://example.test/license"\n' +
    '      }\n' +
    '    ]\n' +
    '  }\n' +
    '}'
);

assert.deepStrictEqual(
  helpers.applyResolvedFields([
    {
      key: 'title',
      currentValue: 'Current title',
      resolvedValue: 'Resolved title',
      apply: true
    },
    {
      key: 'notes',
      currentValue: 'Current notes',
      resolvedValue: 'Resolved notes',
      apply: false
    }
  ]),
  [
    { key: 'title', value: 'Resolved title', changed: true },
    { key: 'notes', value: 'Current notes', changed: false }
  ]
);

assert.deepStrictEqual(
  helpers.applyResolvedFields([
    {
      key: 'title',
      currentValue: 'Existing title',
      resolvedValue: 'Resolved title',
      apply: helpers.defaultApplyState('Existing title')
    }
  ]),
  [
    { key: 'title', value: 'Existing title', changed: false }
  ]
);

assert.deepStrictEqual(
  helpers.applyResolvedFields([
    {
      key: 'instrument_classification',
      currentValue: 'Geophysics',
      resolvedValue: 'Geochemistry',
      apply: helpers.defaultApplyState('Geophysics')
    }
  ]),
  [
    {
      key: 'instrument_classification',
      value: 'Geophysics',
      changed: false
    }
  ]
);

assert.deepStrictEqual(
  helpers.RESOLVED_FIELDS.map(function (field) {
    return [field.key, field.formField];
  }),
  [
    ['identifier_url', 'identifier_url'],
    ['title', 'title'],
    ['notes', 'description'],
    ['instrument_classification', 'instrument_classification']
  ]
);

assert.deepStrictEqual(
  helpers.RESOLVED_FIELDS
    .map(function (field) { return field.key; })
    .filter(function (key) {
      return [
        'alternate_identifier_obj',
        'date',
        'model',
        'related_identifier_obj'
      ].indexOf(key) !== -1;
    }),
  []
);

assert.deepStrictEqual(
  helpers.applyResolvedFields([
    {
      key: 'instrument_classification',
      currentValue: '',
      resolvedValue: 'Geochemistry',
      apply: true
    }
  ]),
  [
    {
      key: 'instrument_classification',
      value: 'Geochemistry',
      changed: true
    }
  ]
);

assert.deepStrictEqual(
  helpers.manualResolvedFields({
    model: [{ model_name: 'GeoProbe 2000' }],
    title: 'Auto-applicable title',
    manufacturer_suggestions: [{ name: 'Thermo Fisher Scientific' }]
  }),
  {
    'Manufacturer Suggestions': [{ name: 'Thermo Fisher Scientific' }]
  }
);

assert.deepStrictEqual(
  helpers.csrfHeaders({
    querySelector: function (selector) {
      var values = {
        'meta[name="csrf_field_name"]': '_csrf_token',
        'meta[name="_csrf_token"]': 'test-token'
      };
      if (!Object.prototype.hasOwnProperty.call(values, selector)) {
        return null;
      }
      return {
        getAttribute: function (name) {
          return name === 'content' ? values[selector] : null;
        }
      };
    }
  }),
  { 'X-CSRFToken': 'test-token' }
);

assert.deepStrictEqual(helpers.csrfHeaders({ querySelector: function () {
  return null;
} }), {});

// Suggestion-only keys must be surfaced by manualResolvedFields but must NOT
// appear in the auto-apply RESOLVED_FIELDS table.
var manualWithSuggestions = helpers.manualResolvedFields({
  instrument_type_suggestions: [{ instrument_type_name: 'MASS SPECTROMETERS' }],
  manufacturer_suggestions: [{ name: 'Thermo Fisher Scientific' }],
  owner_suggestions: [{ name: 'University of Example' }],
  funder_suggestions: [{ funderName: 'ARC' }],
  taxonomy_suggestions: [{ subject: 'Geochemistry' }],
  geo_location_suggestions: [{ geoLocationPlace: 'Perth' }],
  publication_metadata_suggestions: { publisher: 'AuScope', publication_year: '2026' }
});
assert.ok(manualWithSuggestions['Instrument Type Suggestions']);
assert.ok(manualWithSuggestions['Manufacturer Suggestions']);
assert.ok(manualWithSuggestions['Owner Suggestions']);
assert.ok(manualWithSuggestions['Funder Suggestions']);
assert.ok(manualWithSuggestions['Taxonomy Suggestions']);
assert.ok(manualWithSuggestions['Geo Location Suggestions']);
assert.ok(manualWithSuggestions['Publication Metadata Suggestions']);

assert.deepStrictEqual(
  helpers.localMatchGroups({
    manufacturer: [{ match_status: 'exact_unique' }],
    owner: [{ match_status: 'no_match' }]
  }).map(function (group) {
    return [group.key, group.label, group.matches.length];
  }),
  [
    ['manufacturer', 'Manufacturer', 1],
    ['owner', 'Owner', 1],
    ['funder', 'Funder', 0],
    ['instrument_type', 'Instrument type', 0],
    ['measured_variable', 'Measured variable', 0]
  ]
);

assert.strictEqual(helpers.localMatchStatusLabel('exact_unique'), 'Exact match');
assert.strictEqual(helpers.localMatchStatusLabel('ambiguous'), 'Multiple matches');
assert.strictEqual(helpers.localMatchStatusLabel('no_match'), 'No exact match');
assert.strictEqual(
  helpers.normalizeIdentifier(' HTTPS://ROR.ORG/ABC123/ '),
  'https://ror.org/abc123'
);

var exactPartyMatch = {
  group: 'manufacturer',
  match_status: 'exact_unique',
  apply_allowed: true,
  source_identifier: 'https://ror.org/0343ms580',
  source_identifier_type: 'ROR',
  matched_local_id: 'applied-spectra'
};
assert.strictEqual(
  helpers.isEligibleMatch(exactPartyMatch, {
    hasSafeOption: function (group, value) {
      return group === 'manufacturer' && value === 'applied-spectra';
    }
  }),
  true
);
assert.deepStrictEqual(
  helpers.localMatchRejectionReasons(exactPartyMatch, {
    hasSafeOption: function () { return false; }
  }, true),
  ['no safe option/control found']
);
assert.strictEqual(
  helpers.isEligibleMatch({
    group: 'manufacturer',
    match_status: 'no_match',
    apply_allowed: false,
    source_identifier: 'https://ror.org/0343ms580',
    source_identifier_type: 'ROR',
    matched_local_id: ''
  }, {
    hasSafeOption: function () { return true; }
  }),
  false
);
assert.deepStrictEqual(
  helpers.localMatchRejectionReasons({
    group: 'instrument_type',
    match_status: 'exact_unique',
    apply_allowed: true,
    source_identifier: 'https://example.test/term/mass',
    source_identifier_type: 'URI',
    matched_local_id: 'https://example.test/term/mass'
  }, {
    hasSafeOption: function (group, value) {
      return group === 'instrument_type' &&
        value === 'https://example.test/term/mass';
    }
  }, true),
  []
);
assert.strictEqual(
  helpers.vocabEntryMatchesIdentifier(
    { identifier: 'https://example.test/term/mass/' },
    'https://example.test/term/mass'
  ),
  true
);
assert.strictEqual(
  helpers.vocabEntryMatchesIdentifier(
    { name: 'Mass spectrometer' },
    'https://example.test/term/mass'
  ),
  false
);
assert.deepStrictEqual(
  helpers.partyCompositeApplyPlan([
    { value: '', optionValues: ['funder-a', 'funder-b', 'funder-c'] }
  ], ['funder-a', 'funder-b', 'funder-c']),
  {
    values: ['funder-a', 'funder-b', 'funder-c'],
    applied: ['funder-a', 'funder-b', 'funder-c'],
    skipped: []
  }
);
assert.deepStrictEqual(
  helpers.partyCompositeApplyPlan([
    { value: 'funder-a', optionValues: ['funder-a', 'funder-b'] },
    { value: '', optionValues: ['funder-a', 'funder-b'] }
  ], ['funder-a', 'funder-b']),
  {
    values: ['funder-a', 'funder-b'],
    applied: ['funder-a', 'funder-b'],
    skipped: []
  }
);
assert.deepStrictEqual(
  helpers.partyCompositeApplyPlan([
    { value: 'existing-funder', optionValues: ['existing-funder', 'new-funder'] }
  ], ['new-funder']),
  {
    values: ['existing-funder', 'new-funder'],
    applied: ['new-funder'],
    skipped: []
  }
);
assert.deepStrictEqual(
  helpers.partyCompositeApplyPlan([
    { value: '', optionValues: ['known-funder'] }
  ], ['missing-funder']),
  {
    values: [''],
    applied: [],
    skipped: ['missing-funder']
  }
);
assert.strictEqual(
  helpers.partyControlTargetIndex([
    { value: '', optionValues: ['maker-party'] }
  ], 'maker-party'),
  0
);
assert.strictEqual(
  helpers.partyControlTargetIndex([
    { value: 'other-party', optionValues: ['other-party', 'maker-party'] }
  ], 'maker-party'),
  -1
);

var autoApplyKeys = helpers.RESOLVED_FIELDS.map(function (f) { return f.key; });
[
  'instrument_type_suggestions', 'manufacturer_suggestions', 'owner_suggestions',
  'funder_suggestions', 'party_identifier_suggestions', 'taxonomy_suggestions',
  'geo_location_suggestions', 'publication_metadata_suggestions'
].forEach(function (key) {
  assert.strictEqual(
    autoApplyKeys.indexOf(key), -1,
    key + ' must not be auto-applied'
  );
});

assert.deepStrictEqual(
  helpers.SUPPORTED_COMPOSITE_FIELDS.map(function (field) {
    return [field.key, field.subfields];
  }),
  [
    ['model', ['model_name', 'model_identifier', 'model_identifier_type']],
    [
      'alternate_identifier_obj',
      [
        'alternate_identifier_type',
        'alternate_identifier',
        'alternate_identifier_name'
      ]
    ],
    ['date', ['date_value', 'date_type']],
    [
      'related_identifier_obj',
      [
        'related_identifier',
        'related_identifier_type',
        'relation_type',
        'related_identifier_name',
        'related_resource_type'
      ]
    ]
  ]
);

assert.strictEqual(helpers.qualifiesForApply(null), false);
assert.strictEqual(helpers.qualifiesForApply({ model_name: 'GeoProbe' }), false);
assert.strictEqual(helpers.qualifiesForApply([]), false);
assert.strictEqual(helpers.qualifiesForApply([{ model_name: '   ' }]), false);
assert.strictEqual(
  helpers.qualifiesForApply([{ model_name: '   ' }, { model_name: 'GeoProbe' }]),
  true
);

assert.deepStrictEqual(
  helpers.subfieldSignature(
    { model_identifier: '  https://example.test/model  ', model_name: ' GeoProbe ' },
    ['model_name', 'model_identifier', 'model_identifier_type']
  ),
  ['GeoProbe', 'https://example.test/model', '']
);

assert.deepStrictEqual(
  helpers.missingResolvedRows(
    [
      {
        model_name: 'GeoProbe',
        model_identifier: 'https://example.test/model',
        model_identifier_type: 'URL'
      }
    ],
    [
      {
        model_name: ' GeoProbe ',
        model_identifier: ' https://example.test/model ',
        model_identifier_type: ' URL '
      },
      {
        model_name: 'GeoProbe 2',
        model_identifier: '',
        model_identifier_type: ''
      },
      {
        model_name: 'GeoProbe 2',
        model_identifier: '',
        model_identifier_type: ''
      },
      {
        model_name: '   ',
        model_identifier: '',
        model_identifier_type: ''
      }
    ],
    ['model_name', 'model_identifier', 'model_identifier_type']
  ),
  [
    {
      model_name: 'GeoProbe 2',
      model_identifier: '',
      model_identifier_type: ''
    }
  ]
);

assert.strictEqual(
  helpers.defaultCompositeApplyState(
    [{ model_name: '', model_identifier: '   ' }],
    ['model_name', 'model_identifier']
  ),
  true
);
assert.strictEqual(
  helpers.defaultCompositeApplyState(
    [{ model_name: 'Existing model', model_identifier: '' }],
    ['model_name', 'model_identifier']
  ),
  false
);

assert.deepStrictEqual(
  helpers.compositeApplyTargets({
    model: [{ model_name: 'GeoProbe' }],
    date: [{ date_value: '   ' }],
    manufacturer_suggestions: [{ name: 'Thermo Fisher Scientific' }],
    taxonomy_suggestions: [{ subject: 'Geochemistry' }],
    unknown_structured_field: [{ value: 'ignored' }]
  }).map(function (field) { return field.key; }),
  ['model']
);

console.log('doi-resolve helper tests passed');
