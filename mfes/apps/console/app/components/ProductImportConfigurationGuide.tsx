'use client';
import { Notice, ReviewList, SectionHeader, useFormatters } from '@janso/ui';

export function ProductImportConfigurationGuide({ value }: { value: unknown }) {
  const format = useFormatters();
  if (!value || typeof value !== 'object') return null;
  const config = value as {
    kind?: string;
    as_of?: string;
    options?: { key: string; label: string; mode: string }[];
    inventory_profile?: boolean;
    note?: string;
  };
  const labels: Record<string, string> = {
    REQUIRED: 'Required before activation',
    OPTIONAL: 'Optional',
    DISABLED: 'Disabled',
  };
  if (
    !['GOODS', 'SERVICE'].includes(config.kind ?? '') ||
    typeof config.inventory_profile !== 'boolean' ||
    !Array.isArray(config.options) ||
    config.options.some(
      (option) =>
        !option || typeof option.label !== 'string' || !labels[option.mode],
    )
  )
    return (
      <Notice tone="warning">
        Product configuration could not be verified for this template. Download
        a current template.
      </Notice>
    );
  return (
    <div className="janso-flow">
      <SectionHeader title="Product configuration for this template" />
      <ReviewList
        items={[
          {
            label: 'Product kind',
            value: config.kind === 'SERVICE' ? 'Services' : 'Goods',
          },
          ...(/^\d{4}-\d{2}-\d{2}$/.test(config.as_of ?? '')
            ? [
                {
                  label: 'Configuration date',
                  value: format.date(config.as_of!),
                },
              ]
            : []),
          ...config.options.map((option) => ({
            label: option.label,
            value: labels[option.mode]!,
          })),
          {
            label: 'Inventory profile',
            value: config.inventory_profile
              ? 'Configured; applied during activation'
              : 'Not selected in this context',
          },
        ]}
      />
      {typeof config.note === 'string' && (
        <p className="janso-fine">{config.note}</p>
      )}
    </div>
  );
}
