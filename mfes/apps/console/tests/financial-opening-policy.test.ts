import { expect, it } from 'vitest';
import { allowedFinancialOpeningRequest as allow } from '../app/lib/financial-opening-policy';
import { ACCOUNT, BATCH, COMPANY, JOB } from './financial-opening-fixtures';
const root = `/v1/companies/${COMPANY}/opening-batches`, workspace = `${root}/workspaces/${BATCH}`;
it.each([
  ['GET', root + '?limit=25&sort=-id'], ['GET', root + '/' + BATCH],
  ['GET', root + '/readiness'], ['GET', root + '/capabilities'], ['GET', root + '/workspaces/field-set'],
  ['POST', root + '/workspaces'], ['POST', root + '/workspaces/preview'], ['GET', workspace],
  ['GET', workspace + '/declaration'], ['GET', workspace + '/entries?limit=25&account_id=' + ACCOUNT],
  ['GET', workspace + '/revisions?sort=-id'], ['GET', workspace + '/reconciliation'],
  ['GET', workspace + '/entries/' + ACCOUNT + '/posting-link'], ['GET', workspace + '/export?token=signed'],
  ['POST', workspace + '/replace'], ['POST', workspace + '/prepare-drafts'], ['POST', workspace + '/finalize'], ['POST', workspace + '/void'],
  ['POST', `/v1/companies/${COMPANY}/financial-opening-imports`], ['GET', `/v1/companies/${COMPANY}/financial-opening-imports?state=READY`],
  ['POST', `/v1/companies/${COMPANY}/financial-opening-imports/${JOB}/commit`],
  ['GET', `/v1/companies/${COMPANY}/journal-lines?journal_id=${ACCOUNT}`],
  ['POST', `/v1/companies/${COMPANY}/journals/${ACCOUNT}/post`],
  ['POST', `/v1/companies/${COMPANY}/journals/${ACCOUNT}/void`],
  ['POST', `/v1/companies/${COMPANY}/journals/${ACCOUNT}/reversal`],
  ['GET', workspace + `/journals/${ACCOUNT}/recovery`],
])('permits only the fixed opening surface: %s %s', (method, path) => expect(allow('accounting', method!, path!)).toBe(true));
it.each([
  ['catalog', 'GET', root + '/readiness'], ['accounting', 'GET', '//evil.test'],
  ['accounting', 'GET', root + '/readiness?extra=1'], ['accounting', 'GET', workspace + '/entries?limit=201'],
  ['accounting', 'GET', workspace + '/entries?limit=25&limit=50'], ['accounting', 'GET', workspace + '/entries?role=OTHER'],
  ['accounting', 'GET', workspace + '/entries?account_id=not-an-id'], ['accounting', 'GET', workspace + '/entries?q=anything'],
  ['accounting', 'GET', root + '/../journals'], ['accounting', 'GET', root + '/%2e%2e/journals'],
  ['accounting', 'DELETE', workspace], ['accounting', 'DELETE', `/v1/companies/${COMPANY}/journals/${ACCOUNT}`],
  ['accounting', 'GET', workspace + '/export'], ['accounting', 'GET', workspace + '/export?token=a&other=b'],
])('rejects non-opening, ambiguous and malformed requests', (service, method, path) => expect(allow(service!, method!, path!)).toBe(false));
