// The advanced filter panel from SRS 7.1.2, described as data so the drawer,
// the chips and the URL all read from one place.
//
// Every `param` here is a query parameter the backend's LayFilter already
// accepts, so the URL and the API request are the same thing — which is what
// makes "send someone the link and they see your result" work (7.1.2).

export type FilterKind = "text" | "number" | "date" | "select" | "bool";

export type FilterDef = {
  param: string;
  label: string;
  kind: FilterKind;
  options?: { value: string; label: string }[];
  placeholder?: string;
};

export type FilterGroup = { key: string; label: string; filters: FilterDef[] };

export const STATUS_OPTIONS = [
  { value: "open", label: "مفتوحة" },
  { value: "closed", label: "مقفولة" },
  { value: "counted", label: "مترقّمة" },
  { value: "approved", label: "معتمدة" },
];

const YES_NO = [
  { value: "true", label: "نعم" },
  { value: "false", label: "لا" },
];

export const FILTER_GROUPS: FilterGroup[] = [
  {
    key: "time",
    label: "الوقت",
    filters: [
      { param: "date_from", label: "من تاريخ", kind: "date" },
      { param: "date_to", label: "إلى تاريخ", kind: "date" },
    ],
  },
  {
    key: "model",
    label: "الموديل والقسم",
    filters: [
      { param: "code", label: "كود القصة", kind: "text", placeholder: "1749" },
      { param: "category", label: "القسم", kind: "text", placeholder: "رجالي" },
    ],
  },
  {
    key: "sizes",
    label: "المقاسات",
    filters: [
      { param: "size", label: "مقاس موجود في الفرشة", kind: "text", placeholder: "32" },
      { param: "size_count_min", label: "عدد المقاسات من", kind: "number" },
      { param: "size_count_max", label: "إلى", kind: "number" },
    ],
  },
  {
    key: "measure",
    label: "القياسات",
    filters: [
      { param: "lay_length_min", label: "طول الفرشة من", kind: "number" },
      { param: "lay_length_max", label: "إلى", kind: "number" },
      { param: "lay_width_min", label: "عرض الفرشة من", kind: "number" },
      { param: "lay_width_max", label: "إلى", kind: "number" },
      { param: "total_plies_min", label: "إجمالي الراق من", kind: "number" },
      { param: "total_plies_max", label: "إلى", kind: "number" },
    ],
  },
  {
    key: "pieces",
    label: "القطع",
    filters: [
      { param: "theoretical_pieces_min", label: "القطع النظرية من", kind: "number" },
      { param: "theoretical_pieces_max", label: "إلى", kind: "number" },
      { param: "actual_pieces_min", label: "القطع الفعلية من", kind: "number" },
      { param: "actual_pieces_max", label: "إلى", kind: "number" },
      { param: "pieces_loss_pct_min", label: "فاقد القطع % من", kind: "number" },
      { param: "pieces_loss_pct_max", label: "إلى", kind: "number" },
    ],
  },
  {
    key: "metrage",
    label: "الميتراج",
    filters: [
      { param: "expected_metrage_min", label: "المتوقع من", kind: "number" },
      { param: "expected_metrage_max", label: "إلى", kind: "number" },
      { param: "real_metrage_min", label: "الحقيقي من", kind: "number" },
      { param: "real_metrage_max", label: "إلى", kind: "number" },
      { param: "deviation_min", label: "الانحراف % من", kind: "number" },
      { param: "deviation_max", label: "إلى", kind: "number" },
    ],
  },
  {
    key: "fabric",
    label: "القماش",
    filters: [
      { param: "shade_note", label: "اللون", kind: "text", placeholder: "أسود" },
      { param: "total_roll_length_min", label: "إجمالي الأمتار من", kind: "number" },
      { param: "total_roll_length_max", label: "إلى", kind: "number" },
    ],
  },
  {
    key: "remnants",
    label: "البواقي",
    filters: [
      { param: "has_remnants", label: "فيها بواقي؟", kind: "select", options: YES_NO },
      { param: "has_waste_remnants", label: "بواقي هالك؟", kind: "select", options: YES_NO },
      { param: "total_remnant_min", label: "إجمالي البواقي من", kind: "number" },
      { param: "total_remnant_max", label: "إلى", kind: "number" },
    ],
  },
  {
    key: "people",
    label: "الناس",
    filters: [
      { param: "team_leader_name", label: "رئيس الفريق", kind: "text" },
      { param: "bank_code", label: "البنك (كود)", kind: "text" },
    ],
  },
  {
    key: "state",
    label: "الحالة",
    filters: [
      { param: "status", label: "حالة الفرشة", kind: "select", options: STATUS_OPTIONS },
      { param: "has_shortage", label: "فيها عجز؟", kind: "select", options: YES_NO },
      { param: "has_length_mismatch", label: "فيها فرق أطوال؟", kind: "select", options: YES_NO },
      { param: "has_splice", label: "فيها وصل؟", kind: "select", options: YES_NO },
      { param: "quick_entry", label: "إدخال سريع؟", kind: "select", options: YES_NO },
      { param: "is_backfill", label: "مرحّلة؟", kind: "select", options: YES_NO },
      { param: "has_sheet_image", label: "فيها صورة دفتر؟", kind: "select", options: YES_NO },
      { param: "awaiting_count", label: "مستنية ترقيم؟", kind: "select", options: YES_NO },
    ],
  },
];

export const ALL_FILTERS: Record<string, FilterDef> = Object.fromEntries(
  FILTER_GROUPS.flatMap((g) => g.filters).map((f) => [f.param, f])
);

// Params the list owns that are not filters, so "clear all" leaves them alone.
export const NON_FILTER_PARAMS = new Set(["q", "ordering", "page"]);

export function chipLabel(param: string, value: string): string {
  const def = ALL_FILTERS[param];
  if (!def) return `${param}: ${value}`;
  const option = def.options?.find((o) => o.value === value);
  return `${def.label}: ${option?.label ?? value}`;
}

export const STATUS_LABEL: Record<string, string> = Object.fromEntries(
  STATUS_OPTIONS.map((s) => [s.value, s.label])
);

export const STATUS_STYLE: Record<string, string> = {
  open: "bg-slate-100 text-slate-600",
  closed: "bg-sky-100 text-sky-700",
  counted: "bg-emerald-100 text-emerald-700",
  approved: "bg-violet-100 text-violet-700",
};
