'use client';
import { useState, type ReactNode } from 'react';
import {
  ActionCard,
  Button,
  FilterBar,
  Notice,
  PageHeader,
  PageNavigation,
  SectionHeader,
  TableSearch,
} from '@janso/ui';
import type { ReportSection } from '../lib/report-cards';
import {isAnalyticsReport} from '../lib/analytics-workspace';
import { useReportCatalogue } from '../lib/report-catalogue';
const normalized = (value: string) =>
  value
    .toLowerCase()
    .replace(/[_&-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
export function ReportCardCatalogue({
  company,
  root,
  rootTitle,
  title,
  description,
  selected,
  sections: catalogue,
  links,
  icon,
}: {
  company: string;
  root: string;
  rootTitle: 'Books' | 'Reports';
  title: string;
  description: string;
  selected?: string;
  sections: ReportSection[];
  links: { key: string; title: string }[];
  icon: ReactNode;
}) {
  const availability = useReportCatalogue(company);
  const available = new Map(availability.data?.items.map(item => [item.definition.code, item]) ?? []);
  const serviceUnavailable = (availability.failure?.status ?? 0) >= 500;
  const showAnalyticsPreview = availability.loading || serviceUnavailable;
  const showCard = (report: ReportSection['reports'][number]) =>
    available.has(report.code) ||
    (isAnalyticsReport(report.code) && showAnalyticsPreview) ||
    !isAnalyticsReport(report.code);
  const [search, setSearch] = useState(''),
    noun = rootTitle.toLowerCase(),
    singular = noun.slice(0, -1),
    query = normalized(search);
  const directMatch = (report: ReportSection['reports'][number]) =>
    normalized(
      report.title + ' ' + report.code + ' ' + report.description,
    ).includes(query);
  const hasDirectMatch = catalogue.some((section) =>
    section.reports.some(report => showCard(report) && directMatch(report)),
  );
  const sections = catalogue
    .map((section) => ({
      ...section,
      reports: section.reports.filter(
        (report) =>
          showCard(report) && (directMatch(report) ||
          (!hasDirectMatch &&
            normalized(section.title + ' ' + section.description).includes(
              query,
            ))),
      ),
    }))
    .filter((section) => section.reports.length);
  return (
    <div className="janso-page">
      <PageNavigation
        back={{
          href: selected ? root : '/',
          label: selected ? noun : 'business overview',
        }}
        breadcrumbs={[
          { label: 'Business overview', href: '/' },
          ...(selected ? [{ label: rootTitle, href: root }] : []),
          { label: title },
        ]}
      />
      <PageHeader title={title} lede={description} />
      <nav
        className="janso-page-navigation"
        aria-label={rootTitle === 'Reports' ? 'Report categories' : 'Books'}
      >
        <a
          className="janso-link"
          href={root}
          aria-current={!selected ? 'page' : undefined}
        >
          All {noun}
        </a>
        {links.map((link) => (
          <a
            key={link.key}
            className="janso-link"
            href={root + '/' + link.key}
            aria-current={selected === link.key ? 'page' : undefined}
          >
            {link.title}
          </a>
        ))}
      </nav>
      <FilterBar>
        <TableSearch
          label={'Search ' + noun}
          placeholder={'Search by full or partial ' + singular + ' name'}
          value={search}
          onChange={setSearch}
          minLength={0}
          maxLength={120}
          showLabel={rootTitle === 'Reports'}
        />
      </FilterBar>
      {availability.loading && <Notice>Checking report availability…</Notice>}
      {availability.failure && <Notice tone="warning">Report availability could not be loaded. <Button variant="ghost" onClick={availability.refresh}>Retry report availability</Button></Notice>}
      {!availability.loading && !availability.failure && <Notice>Open an available {singular} to select its period and source. New runs require a verified source snapshot.</Notice>}
      {!sections.length ? (
        <Notice>
          No {noun} match your search. Clear the search to see all {singular}{' '}
          cards in this section.
        </Notice>
      ) : (
        sections.map((section) => (
          <section
            key={section.title}
            className="janso-flow"
            aria-label={section.title}
          >
            <SectionHeader
              title={section.title}
              description={section.description}
            />
            <div className={'janso-action-card-grid' + (rootTitle === 'Reports' ? ' janso-action-card-grid--compact' : '')}>
              {section.reports.map((report) => {
                const needsGstSetup = !available.has(report.code) && !availability.loading && !availability.failure && ['GSTR3B','GSTR1'].includes(report.code);
                return (
                <ActionCard
                  key={report.code}
                  title={report.title}
                  description={report.description + (needsGstSetup ? ' Requires an eligible Indian GST registration and report access for this company.' : '')}
                  icon={icon}
                  {...(available.has(report.code)
                    ? { href: report.code === 'DAY_BOOK' && rootTitle === 'Books' ? '/books/day-book' : '/reports/workspace?report=' + encodeURIComponent(report.code), actionLabel: available.get(report.code)!.run_enabled ? 'Open report' : 'View completed reports' }
                    : { actionLabel: availability.loading ? 'Checking availability' : serviceUnavailable ? 'Report service unavailable' : needsGstSetup ? 'GST setup or access required' : 'Unavailable with current access', disabledReason: availability.loading ? 'Loading' : serviceUnavailable ? 'Service unavailable' : needsGstSetup ? 'Setup or access required' : 'Unavailable', unavailableAction:needsGstSetup ? {href:'/companies/'+encodeURIComponent(company)+'/gst-settings',label:'Set up GST'} : undefined })}
                />
              );})}
            </div>
          </section>
        ))
      )}
    </div>
  );
}
