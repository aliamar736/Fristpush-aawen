export type Paged<T> = { count: number; next: string | null; previous: string | null; results: T[] };

export type RoleAssignment = { id: number; role: string; role_label: string; area: number | null; area_name: string | null;
  agency: number | null; agency_name: string | null; active: boolean };
export type Me = { id: number; username: string; phone: string | null; display_name: string; roles: RoleAssignment[];
  pending_deletion: string | null; preferred_language: string; is_demo: boolean };

export type Category = { id: number; slug: string; name_ar: string; name_en: string; layer: string; hazard_weight: number;
  icon: string; keywords: string[]; sort_order: number; active: boolean; followup_days: number | null };

export type MediaRef = { uid: string; kind: string; role: string; status: string; url: string; added_at?: string };

export type ReportEvent = { id: number; at: string; kind: string; from_status: string; to_status: string; to_label: string;
  note: string; actor: string };

export type Report = {
  id: number; tracking_number: string | null; category: { id: number; slug: string; name: string; layer: string; icon: string };
  status: string; status_label: string; lat: number; lng: number; area: number | null; area_name: string | null;
  agency_name: string | null; landmark_text: string; description: string | null; observed_at: string;
  submitted_at: string | null; status_changed_at: string; confirmations_count: number; reopen_count: number;
  priority_score: number; danger_level: number; resolved_at: string | null; media: MediaRef[]; is_demo: boolean;
  distance_m?: number;
  // detail
  events?: ReportEvent[]; referral?: { agency: string; referred_at: string; acknowledged_at: string | null;
    agency_linked: boolean; channel: string } | null;
  completion?: { round: number; proofs: { note: string; at: string }[]; checks: { fixed: number; not_fixed: number; partial: number } };
  actions?: string[]; viewer?: { authenticated: boolean; is_owner?: boolean; kinds?: string[]; confirmed?: boolean;
    checked?: boolean; is_executor?: boolean };
  needs_info_question?: string; status_reason?: string; resolution_round?: number; open_objections?: number;
  // staff
  reporter_name?: string | null; raw_description?: string; routing_status?: string; routing_notes?: string;
  routing_candidates?: { area_id: number; area: string; agency_id: number | null; agency: string | null }[];
  agency?: number | null; sensitive_flags?: string[]; priority_breakdown?: Record<string, number | string>;
  field_assignee?: number | null; follow_up_owner?: number | null; escalated_at?: string | null; all_media?: MediaRef[];
  internal_events?: { at: string; kind: string; note: string; actor_role: string; data: Record<string, unknown> }[];
};

export type MapReport = { id: number; tracking_number: string; category_id: number; status: string; lat: number; lng: number;
  submitted_at: string; priority_score: number; is_demo: boolean };

export type RoadAlert = { id: number; type: string; type_label: string; lat: number; lng: number; description: string;
  direction: string; observed_at: string; reported_at: string; last_confirmed_at: string; expires_at: string; source: string;
  source_label: string; verification: string; verification_label: string; status: string; status_label: string;
  still_there_count: number; cleared_count: number; minutes_since_confirmed: number; is_live: boolean; is_demo: boolean;
  notice?: string };

export type Area = { id: number; name_ar: string; name_en: string; slug: string; population: number | null;
  boundary_source: string; centroid: { lat: number; lng: number }; geometry: GeoJSON.MultiPolygon | null; is_demo: boolean };

export type Need = { id: number; initiative: number; initiative_title: string; kind: string; kind_label: string; title: string;
  details: string; quantity_needed: string; quantity_fulfilled: string; unit: string; is_blocking: boolean; status: string;
  offers_count: number };

export type Initiative = { id: number; title: string; summary: string; description: string; area: number | null;
  area_name: string | null; point: { lat: number; lng: number } | null; status: string; status_label: string;
  manager_name: string | null; starts_at: string | null; funding_target: string; needs: Need[]; results_summary: string;
  finance: null | { funding_target: string; pledged_total: string; collected: string; fees: string; disbursed: string;
    refunded: string; balance: string; contributors: number; simulated_entries: number; corporate_contributors: number };
  is_manager: boolean; created_at: string; is_demo: boolean };

export type Task = { id: number; initiative: number | null; title: string; description: string; point: { lat: number; lng: number } | null;
  area: number | null; location_text: string; starts_at: string; duration_minutes: number; skill: number | null;
  skill_name: string | null; owner_name: string | null; capacity: number; status: string; booked: number;
  my_booking: { id: number; status: string } | null; match_reasons: string[] | null; is_demo: boolean };

export type Resource = { id: number; title: string; description: string; kind: string; kind_label: string; unit: string;
  total_quantity: number; reserved_quantity: number; out_quantity: number; consumed_quantity: number;
  available_quantity: number; condition: string; custodian_name: string | null; pickup_location: string;
  max_loan_days: number; can_manage: boolean; is_demo: boolean };

export type Reservation = { id: number; resource: number; resource_title: string; resource_kind: string; user_name: string;
  quantity: number; status: string; purpose: string; pickup_by: string | null; due_return_at: string | null;
  picked_up_at: string | null; returned_at: string | null; pickup_location: string; created_at: string };

export type Payment = { id: number; provider: string; provider_payment_id: string; amount: string; fee: string; status: string;
  failure_reason: string; receipt_number: string | null; is_simulated: boolean; checkout_url: string; confirmed_at: string | null;
  refunded_amount: string; created_at: string };

export type Pledge = { id: number; initiative: number; initiative_title: string; need: number | null; amount: string;
  method: string; status: string; status_label: string; organization_name: string; is_corporate: boolean;
  payments: Payment[]; transfer_proofs: { id: number; status: string; claimed_reference: string }[]; created_at: string };

export type Notification = { id: number; kind: string; title: string; body: string; data: Record<string, unknown>;
  created_at: string; read_at: string | null };

export type PublicConfig = { env: string; demo_data_allowed: boolean; features: Record<string, boolean>;
  emergency_notice: { ar: string; en: string; contacts: { name: string; phone: string }[] };
  payments: { mode: string; accepting_real_money: boolean; message: string; missing?: string[] };
  finance_policies: Record<string, string>; integrations: Record<string, string> };
