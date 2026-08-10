"use client";

import { useMemo } from "react";
import { Group, Layer, Line, Rect, Stage, Text } from "react-konva";

export type TemplateGuide = {
  label: string;
  width: number;
  height: number;
  safeArea: number;
};

export function ImageTemplateEditor({guide}: {guide: TemplateGuide}) {
  const size = 360;
  const ratio = guide.width / guide.height;
  const frame = useMemo(
    () => (ratio >= 1 ? {width: size, height: size / ratio} : {width: size * ratio, height: size}),
    [ratio],
  );
  const x = (420 - frame.width) / 2;
  const y = (420 - frame.height) / 2;
  const inset = Math.min(frame.width, frame.height) * guide.safeArea;

  return (
    <div className="overflow-hidden rounded-xl border border-[#dfe4ec] bg-[#e9edf4]">
      <Stage width={420} height={420} className="mx-auto max-w-full">
        <Layer>
          <Rect x={0} y={0} width={420} height={420} fill="#e9edf4" />
          {Array.from({length: 13}).map((_, index) => (
            <Line
              key={`v-${index}`}
              points={[index * 35, 0, index * 35, 420]}
              stroke="#dce2eb"
              strokeWidth={1}
            />
          ))}
          {Array.from({length: 13}).map((_, index) => (
            <Line
              key={`h-${index}`}
              points={[0, index * 35, 420, index * 35]}
              stroke="#dce2eb"
              strokeWidth={1}
            />
          ))}
          <Group>
            <Rect x={x} y={y} width={frame.width} height={frame.height} fill="#fff" shadowBlur={18} shadowOpacity={0.08} />
            <Rect x={x + inset} y={y + inset} width={frame.width - inset * 2} height={frame.height - inset * 2} stroke="#ff6433" dash={[8, 6]} strokeWidth={2} />
            <Rect x={x + frame.width * 0.29} y={y + frame.height * 0.2} width={frame.width * 0.42} height={frame.height * 0.54} cornerRadius={18} fill="#dfe7df" stroke="#a9b8aa" />
            <Line points={[x + frame.width * 0.39, y + frame.height * 0.33, x + frame.width * 0.61, y + frame.height * 0.33]} stroke="#93a797" strokeWidth={7} lineCap="round" />
            <Text x={x + 14} y={y + frame.height - 26} text={`${guide.width} × ${guide.height}px`} fill="#667085" fontSize={12} fontFamily="Bahnschrift" />
          </Group>
          <Text x={18} y={18} text={guide.label.toUpperCase()} fill="#172033" fontSize={12} fontStyle="bold" fontFamily="Bahnschrift" letterSpacing={1.5} />
        </Layer>
      </Stage>
    </div>
  );
}

