/** Model ids are namespaced ("vendor/name"); screens show only the short name. */
export function modelLabel(modelId: string): string {
  return modelId.split('/').pop() ?? modelId;
}
