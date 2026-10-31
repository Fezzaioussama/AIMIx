import { FACT_LABELS, type OperatorFacts } from './operator';

/** `{{name}}` in a legal document stands for the operator fact of that name. */
const PLACEHOLDER = /\{\{(\w+)\}\}/g;

function isFact(key: string, facts: OperatorFacts): key is keyof OperatorFacts {
  return Object.hasOwn(facts, key);
}

/**
 * The document with each `{{fact}}` replaced by the operator's value, or by a visible
 * "[à compléter : …]" marker while that fact is missing, so a gap is never silent.
 */
export function fillFacts(template: string, facts: OperatorFacts): string {
  return template.replace(PLACEHOLDER, (whole, key: string) => {
    if (!isFact(key, facts)) throw new Error(`Unknown operator fact ${whole}`);
    return facts[key] ?? `**[à compléter : ${FACT_LABELS[key]}]**`;
  });
}

/** The facts a set of documents still lacks, for the checklist and the tests. */
export function missingFacts(facts: OperatorFacts): (keyof OperatorFacts)[] {
  return (Object.keys(facts) as (keyof OperatorFacts)[]).filter((key) => facts[key] === null);
}
