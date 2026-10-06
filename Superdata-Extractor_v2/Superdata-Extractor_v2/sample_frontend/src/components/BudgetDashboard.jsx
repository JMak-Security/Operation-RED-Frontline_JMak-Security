import { useState } from "react";
import { fetchBudgets, createBudget } from "../api/budgetApi";

const initialState = {
  budgets: [],
  loading: false,
  error: null,
  selectedId: null,
};

export function BudgetDashboard() {
  const [state, setState] = useState(initialState);

  async function loadData() {
    setState({ ...state, loading: true });
    const data = await fetchBudgets();
    setState({ ...state, budgets: data.items, loading: false });
  }

  return (
    <div>
      <h1>Budget Dashboard</h1>
      <BudgetForm onSubmit={createBudget} />
      <BudgetList items={state.budgets} />
    </div>
  );
}

export function BudgetForm({ onSubmit }) {
  return (
    <form>
      <input type="text" name="department" required placeholder="Department" />
      <input type="number" name="amount" required placeholder="Amount (USD)" />
      <textarea name="notes" placeholder="Notes" />
      <select name="quarter">
        <option value="Q1">Q1</option>
        <option value="Q2">Q2</option>
      </select>
      <button type="submit">Save</button>
    </form>
  );
}

export function BudgetList({ items }) {
  return (
    <ul>
      {items.map((item) => (
        <li key={item.id}>{item.department}: ${item.amount}</li>
      ))}
    </ul>
  );
}
