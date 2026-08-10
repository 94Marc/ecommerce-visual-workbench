export const imageSlots = [
  {code: "MAIN", label: "主图", width: 1600, height: 1600, safeArea: 0.08},
  {code: "DETAIL", label: "详情图", width: 1600, height: 1600, safeArea: 0.06},
  {code: "DIMENSION", label: "尺寸图", width: 1600, height: 1600, safeArea: 0.08},
  {code: "SCENE", label: "场景图", width: 1600, height: 1600, safeArea: 0.04},
  {code: "USAGE", label: "使用图", width: 1600, height: 1600, safeArea: 0.06},
  {code: "PACKAGE", label: "包装图", width: 1600, height: 1600, safeArea: 0.08},
  {code: "CLOSEUP", label: "细节图", width: 1600, height: 1600, safeArea: 0.06},
  {code: "COMPARE", label: "卖点图", width: 1600, height: 1600, safeArea: 0.08},
] as const;

export type ImageSlotCode = (typeof imageSlots)[number]["code"];

export function findTemplate(code: ImageSlotCode) {
  return imageSlots.find((slot) => slot.code === code) ?? imageSlots[0];
}
