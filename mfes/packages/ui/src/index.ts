/**
 * @janso/ui — shared design system, reused across every JANSO micro-frontend.
 * The contract for everything here is docs/design-system.md.
 *
 * Consumers must also import the stylesheets once, in this order — non-colour tokens, then
 * every palette, then the components that consume them:
 *   import '@janso/ui/styles/tokens.css';
 *   import '@janso/ui/styles/theme-light.css';
 *   import '@janso/ui/styles/theme-dark.css';
 *   import '@janso/ui/styles/theme-ledger.css';
 *   import '@janso/ui/styles/janso-ui.css';
 *   import '@janso/ui/styles/theme.css';
 *   import '@janso/ui/styles/shell.css';
 *   import '@janso/ui/styles/data.css';
 *   import '@janso/ui/styles/search-select.css';
 *   import '@janso/ui/styles/file-upload.css';
 *   import '@janso/ui/styles/chart.css';
 *   import '@janso/ui/styles/overlay.css';
 *   import '@janso/ui/styles/table.css';
 * and wrap the app in an element carrying the `janso-root` class.
 *
 * All three palettes ship in every build: switching themes must not need a reload, so it
 * cannot need a different stylesheet.
 */

/* ---------- theme ---------- */
export {
  THEME_PREFERENCES,
  THEME_COOKIE,
  THEME_STORAGE_KEY,
  PREFERS_DARK_QUERY,
  isThemePreference,
  resolveTheme,
  colorSchemeFor,
  readStoredPreference,
  persistPreference,
  applyTheme,
  themeScript,
} from './lib/theme';
export type { ThemePreference, ResolvedTheme } from './lib/theme';
export { ThemeProvider, useTheme } from './components/ThemeProvider';
export { ThemeSwitcher } from './components/ThemeSwitcher';
export { Stepper } from './components/Stepper';
export type { StepperStep } from './components/Stepper';
export { WizardLayout, FieldGrid, ReviewList } from './components/WizardLayout';

/* ---------- display config, formatting, permissions ---------- */
export {
  EM_DASH,
  DEFAULT_DISPLAY_CONFIG,
  roundDecimalString,
  groupDigits,
  formatMoney,
  formatQuantity,
  formatPercent,
  formatCompact,
  formatAxisDate,
  formatDate,
  formatDateTime,
  businessToday,
  formatRange,
  formatRelative,
} from './lib/format';
export type {
  DisplayConfig,
  RoundingMode,
  DigitGrouping,
  CurrencyDisplay,
  CurrencySymbolPosition,
  NegativeFormat,
  MoneyOptions,
} from './lib/format';
export { DisplayConfigProvider, useDisplayConfig, useFormatters } from './lib/display-config';
export {resolvedDisplay} from './lib/resolved-display';
export type {ResolvedDisplay} from './lib/resolved-display';
export type { Formatters } from './lib/display-config';
export {
  PermissionProvider,
  usePermissions,
  useCan,
  useGranted,
  Can,
} from './lib/permissions';
/* The scheme allowlist for any href that came from a payload. Exported because an app rendering a
 * link from server data needs the same check, and a second implementation is the one that is wrong. */
export { isSafeHref } from './lib/url';
/* One plural rule for the platform's copy. Exported for the same reason as the formatters: a screen
 * writing "3 companys" beside a table that says "3 companies" is one rule applied twice. */
export { pluralNoun, pluralOf } from './lib/text';
export { usePlacement } from './lib/placement';
export type { Placement, PlacementOptions } from './lib/placement';
export { currentYear } from './lib/date';

/* ---------- shell ---------- */
export { AppShell } from './components/AppShell';
export { Rail, RailSection, RailItem, RailGroup, RailFooter } from './components/Rail';
export { OrgSwitcher } from './components/OrgSwitcher';
export { ContextSwitcher } from './components/ContextSwitcher';
export type { ContextOption, ContextAction } from './components/ContextSwitcher';
export { TopBar } from './components/TopBar';
export { ContextChip, RoleChip } from './components/Chips';
export type { ChipTone } from './components/Chips';
export { NotificationBell } from './components/NotificationBell';
export { UserMenu } from './components/UserMenu';
export type { UserMenuItem } from './components/UserMenu';
export { Avatar } from './components/Avatar';
export type { AvatarShape, AvatarSize } from './components/Avatar';
export { CollapseToggle } from './components/CollapseToggle';
export { AppFooter } from './components/AppFooter';
export type { AppFooterLink } from './components/AppFooter';

/* ---------- content and data ---------- */
export { PageHeader } from './components/PageHeader';
export { PageNavigation } from './components/PageNavigation';
export type { BreadcrumbItem, PageNavigationProps } from './components/PageNavigation';
export { SectionHeader } from './components/SectionHeader';
export { Toolbar } from './components/Toolbar';
export { Tabs, tabButtonId } from './components/Tabs';
export type { Tab } from './components/Tabs';
export { Card, CardHeader, CardBody, CardFooter } from './components/Card';
export { FormLayout, FormActions } from './components/FormLayout';
export type { FormLayoutProps, FormActionsProps } from './components/FormLayout';
export { StatTile, StatRow } from './components/StatTile';
export { Sparkline } from './components/Sparkline';
export type { SparklineProps } from './components/Sparkline';
export type { StatTone } from './components/StatTile';
export { Badge } from './components/Badge';
export type { Tone } from './components/Badge';
export { ListRow } from './components/ListRow';
export { Meter } from './components/Meter';
export { PreparationProgress } from './components/PreparationProgress';
export { Disclosure } from './components/Disclosure';
export { Select } from './components/Select';
export type { SelectOption, SelectOptionGroup, SelectItem } from './components/Select';
export { SearchSelect } from './components/SearchSelect';
export type {
  SearchSelectOption,
  SearchSelectLoader,
  SearchSelectProps,
} from './components/SearchSelect';
export { EntryGrid } from './components/EntryGrid';
export type {
  EntryCellContext,
  EntryCellKind,
  EntryColumn,
  EntryGridProps,
  EntryRowState,
} from './components/EntryGrid';
export { AmountField, QuantityField } from './components/NumericField';
export type { AmountFieldProps, QuantityFieldProps } from './components/NumericField';
export {
  STORAGE_SCALE,
  canonicalise,
  settle,
  storable,
  useNumericInput,
} from './lib/numeric-input';
export type { NumericInputOptions, NumericInputState, NumericKind } from './lib/numeric-input';
export { Menu } from './components/Menu';
export type { MenuItem } from './components/Menu';
export { ConfirmDialog } from './components/ConfirmDialog';
export { Modal, Drawer } from './components/Overlay';
export { CommandPalette, CommandTrigger, useCommandPaletteShortcut } from './components/CommandPalette';
export type { CommandItem, CommandPaletteProps } from './components/CommandPalette';
export type { OverlaySize } from './components/Overlay';
export { useDialogA11y, FOCUSABLE_SELECTOR } from './lib/dialog';
export type { UseDialogA11yOptions, DialogA11y } from './lib/dialog';
export { FilterChip } from './components/FilterChip';
export { FilterBar } from './components/FilterBar';
export type { AppliedFilter } from './components/FilterBar';
export { Notice, TONE_ICONS } from './components/Notice';
export type { NoticeTone } from './components/Notice';
export { ToastProvider, useToast } from './components/Toast';
export type { ToastApi, ToastOptions, ToastPlacement, ToastTone } from './components/Toast';
export { DataTable } from './components/DataTable';
export type { DataTableProps } from './components/DataTable';
export { TableSearch } from './components/TableSearch';
export type { TableSearchProps } from './components/TableSearch';
export { Pager, PAGE_LIMITS } from './components/Pager';
export type { PagerProps } from './components/Pager';
export { BulkBar } from './components/BulkBar';
export type { BulkBarProps } from './components/BulkBar';
export { ColumnPicker } from './components/ColumnPicker';
export type { ColumnPickerProps } from './components/ColumnPicker';
export { ExportMenu, EXPORT_FORMATS } from './components/ExportMenu';
export type { ExportFormat, ExportMenuProps } from './components/ExportMenu';
export { useColumnPreferences, columnPrefsKey } from './lib/column-prefs';
export type { ColumnPreferences } from './lib/column-prefs';
export type {
  CellAlign,
  CellType,
  Column,
  Density,
  Sort,
  SortDirection,
} from './lib/table';
export { firstDirection, nextSort, sortedBy } from './lib/table';
export {
  columnsFromFieldSet,
  CUSTOM_FIELDS_BAG,
  CUSTOM_FIELD_PREFIX,
} from './lib/field-columns';
export type { FieldColumnOptions, FieldDescriptorLike } from './lib/field-columns';
export {
  useListQuery,
  parseListQuery,
  listQueryString,
  serializeSort,
  parseSort,
  clampLimit,
  LIMIT_DEFAULT,
  LIMIT_MAX,
  SEARCH_MIN,
  SEARCH_MAX,
  SORT_FIELDS_MAX,
  FILTER_VALUES_MAX,
} from './lib/list-query';
export type {
  FilterValue,
  ListFilters,
  ListQuery,
  ListQueryHandle,
  PageMeta,
  UseListQueryOptions,
} from './lib/list-query';
export { EmptyState, ErrorState, Skeleton, asErrorStatus } from './components/States';
export type { ErrorStatus } from './components/States';
export { BarChart } from './components/BarChart';
export type { BarChartDatum, BarChartSeries, BarChartProps } from './components/BarChart';
export { GroupedBarChart } from './components/GroupedBarChart';
export type { GroupedBarSeries, GroupedBarChartProps } from './components/GroupedBarChart';

/* ---------- form primitives ---------- */
export { Button } from './components/Button';
export { SplitButton } from './components/SplitButton';
export type { SplitButtonProps } from './components/SplitButton';
export { IconButton } from './components/IconButton';
export { TextField } from './components/TextField';
export { PasswordField, assessPassword, scorePassword } from './components/PasswordField';
export type { PasswordAssessment } from './components/PasswordField';
export { EmailField, isEmailLike, normalizeEmail } from './components/EmailField';
export {
  PhoneField,
  isPhoneLike,
  nationalMaxLength,
  splitInternational,
  toE164,
} from './components/PhoneField';
export type { PhoneDialCode, PhoneValue } from './components/PhoneField';
export { Checkbox } from './components/Checkbox';
export { FileUpload, formatBytes } from './components/FileUpload';
export type {
  FileUploadItem,
  FileUploadStatus,
  FileRejection,
  FileRejectionReason,
} from './components/FileUpload';

/* ---------- brand ---------- */
export { JansoMark } from './components/JansoMark';
export { Wordmark } from './components/Wordmark';

/* ---------- icons ---------- */
export {
  AlertIcon,
  BackIcon,
  BoxIcon,
  CheckIcon,
  EyeIcon,
  EyeOffIcon,
  FacebookIcon,
  GoogleIcon,
  LockIcon,
  MailIcon,
  PhoneIcon,
  ReceiptIcon,
  ScaleIcon,
  ShieldIcon,
  StoreIcon,
  UserIcon,
} from './components/icons';
export {
  ActivityIcon,
  ArrowRightIcon,
  AuditIcon,
  BellIcon,
  BookIcon,
  CalendarIcon,
  CheckCircleIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  ChevronUpDownIcon,
  ClockIcon,
  CloseIcon,
  ContrastIcon,
  CustomersIcon,
  DashboardIcon,
  DocumentIcon,
  DownloadIcon,
  ExternalLinkIcon,
  FilterIcon,
  HelpIcon,
  InfoIcon,
  LogoutIcon,
  MenuIcon,
  MessageIcon,
  MonitorIcon,
  MoonIcon,
  MoreIcon,
  PanelCollapseIcon,
  PaymentsIcon,
  RefreshIcon,
  ReportsIcon,
  RolesIcon,
  SearchIcon,
  SettingsIcon,
  StockIcon,
  SunIcon,
  TaxIcon,
  TrendUpIcon,
  UploadIcon,
  WalletIcon,
  WarnTriangleIcon,
  XCircleIcon,
} from './components/icons-console';
export {
  ChevronLeftIcon,
  ChevronUpIcon,
  ChevronsLeftIcon,
  ChevronsRightIcon,
  ColumnsIcon,
  CopyIcon,
  DensityIcon,
  DragHandleIcon,
  EditIcon,
  MoreVerticalIcon,
  PinIcon,
  PlusIcon,
  TrashIcon,
} from './components/icons-table';

export { CustomFields } from "./components/CustomFields";
export { customCondition, customPatch, customValue } from "./lib/custom-fields";
export type { CustomField, CustomDefinition } from "./lib/custom-fields";

export { CustomFieldEditor } from "./components/CustomFieldEditor";
export type { DefinitionDraft } from "./components/CustomFieldEditor";

export { AttributeValueInput, attributeValue, type NativeAttributeValue, type NativeAttributeField } from './components/AttributeValueInput';
export { ActionCard } from './components/ActionCard';
export { GlobeIcon, MapIcon } from './components/icons-console';

/* ---------- invoice designer canvas ----------
 * The paper, its instruments and its geometry. The *document* renderer (which knows what
 * an invoice is) stays in the app that owns the designer until a second one needs it. */
export { DesignCanvas } from './components/DesignCanvas';
export type { CanvasCursor } from './components/DesignCanvas';
export { CanvasRuler } from './components/CanvasRuler';
export { HANDLES, moveRect, resizeRect, alignmentGuides } from './lib/transform';
export type { Handle, MmRect, Guide, GuideResult, TransformBounds, TransformOptions } from './lib/transform';
export { SelectionLayer } from './components/SelectionLayer';
export { GuideLayer } from './components/GuideLayer';
export type {
  SelectionTarget,
  SelectionCommand,
  TargetRect,
  TransformGesture,
} from './components/SelectionLayer';
export { InspectorGroup, InspectorRow, InspectorEmpty, Kbd } from './components/Inspector';
export { FieldLabel } from './components/FieldLabel';
export { FieldGroup, FieldPair } from './components/FieldGroup';
export { ChoiceCard } from './components/ChoiceCard';
export { PaperThumbnail } from './components/PaperThumbnail';
export {
  MeasureField,
  SegmentedControl,
  ColourField,
  Toggle,
  EditorSelect,
  EditorTextField,
  InspectorStack,
} from './components/EditorControls';
export type { SegmentedOption } from './components/EditorControls';
export { ZoomControl } from './components/ZoomControl';
export {
  PX_PER_MM,
  PAPER_SIZES,
  DEFAULT_MARGINS,
  ZOOM_STEPS,
  MIN_ZOOM,
  MAX_ZOOM,
  clampZoom,
  zoomIn,
  zoomOut,
  fitZoom,
  pxPerMm,
  toMm,
  roundMm,
  snapMm,
  formatMm,
  rulerTicks,
  pageGeometry,
  printableArea,
  rectsOverlap,
} from './lib/paper';
export type {
  PaperSize,
  PaperSpec,
  PaperDefinition,
  PageGeometry,
  Orientation,
  Margins,
  Rect,
} from './lib/paper';
