export type SearchMode = "Category" | "Item Name";
export type TargetType = "Hardware" | "Game";
export type ScanStatus = "queued" | "scanning" | "evaluating" | "saving" | "completed" | "failed";

export interface Target {
  id: string;
  owner_id: string;
  item_name: string;
  category: string;
  search_mode: SearchMode;
  retail_price: number | null;
  deal_price: number;
  downsizing_keywords: string[];
  freebie_keywords: string[];
  notes: string;
  target_type: TargetType;
  allow_bundle_check: boolean;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface ScanRun {
  id: string;
  owner_id: string;
  status: ScanStatus;
  listings_count: number;
  candidates_count: number;
  deals_count: number;
  safe_error: string | null;
  target_snapshot: Record<string, unknown>[];
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  updated_at: string;
}

export interface Listing {
  id: string;
  scan_run_id: string;
  owner_id: string;
  source_listing_id: string;
  title: string;
  price: number | null;
  condition: string;
  description: string;
  link: string;
  seller: string;
  category: string;
  thumbnail_url: string | null;
  seller_rating: number | null;
  seller_rating_count: number | null;
  like_count: number | null;
  location: string | null;
  listing_timestamp: string | null;
  price_flag: string;
  created_at: string;
}

export interface Evaluation {
  id: string;
  scan_run_id: string;
  listing_id: string;
  owner_id: string;
  target_id: string | null;
  target_snapshot_id: string;
  target_snapshot: Record<string, unknown>;
  accepted: boolean;
  matched_item: string | null;
  confidence: number | null;
  specs_matched: boolean | null;
  issues: string[];
  freebies: string[];
  final_condition: string | null;
  deal_price: number | null;
  retail_price: number | null;
  evaluated_price: number | null;
  savings: number | null;
  audit_source: string | null;
  local_match_score: number | null;
  acceptance_reason: string | null;
  is_bundle: boolean;
  individual_price: number | null;
  price_evidence: string | null;
  condition_overridden: boolean;
  created_at: string;
}

export interface InitialData {
  targets: Target[];
  scans: ScanRun[];
  listings: Listing[];
  evaluations: Evaluation[];
}
