export const CATEGORY_OPTIONS = ["", "Reward", "Poll-Bid War", "Target"];
export const VALID_OPTIONS = ["", "Yes", "No", "Needs Review"];
export const STATUS_OPTIONS = [
  "",
  "To-Do",
  "In Review",
  "Needs Information",
  "Approved",
  "Removed",
];

export const STATUS_PILL: Record<string, string> = {
  Approved: "pill pill-approve",
  "In Review": "pill pill-review",
  "To-Do": "pill pill-todo",
  Removed: "pill pill-remove",
  "Needs Information": "pill pill-review",
};
