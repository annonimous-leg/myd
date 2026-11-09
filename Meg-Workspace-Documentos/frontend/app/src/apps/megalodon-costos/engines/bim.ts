export interface BIMElement {
  id: string;
  globalId?: string;
  type: string;
  conceptKey: string;
  description: string;
  unit: string;
  quantity: number;
  cost?: number;
}

/** Maps quantities received from the real BIM backend into CostOS lines. */
export function mapBIMElementsToBudgetLines(elements: BIMElement[]) {
  return elements.map((el, index) => ({
    id: el.id || `BIM-${index + 1}`,
    conceptKey: el.conceptKey,
    description: el.description,
    unit: el.unit,
    quantity: el.quantity,
    unitPrice: el.quantity > 0 && el.cost != null ? el.cost / el.quantity : 0,
    amount: el.cost ?? 0,
    status: el.cost != null && el.quantity > 0 ? 'validated' as const : 'pending' as const,
  }));
}
