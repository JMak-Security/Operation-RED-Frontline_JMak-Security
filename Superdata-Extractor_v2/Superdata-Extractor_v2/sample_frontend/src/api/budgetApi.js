import { API_BASE } from "../config/settings.js";

export async function fetchBudgets() {
  const res = await fetch(`${API_BASE}/budgets`);
  return res.json();
}

export async function createBudget(payload) {
  return fetch("/api/budgets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function updateBudget(id, payload) {
  return axios.put(`/api/budgets/${id}`, payload);
}

export async function deleteBudget(id) {
  return axios.delete(`/api/budgets/${id}`);
}
