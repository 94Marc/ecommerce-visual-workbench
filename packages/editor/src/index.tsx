"use client";

import {
  assetBindingUrl,
  previewDocument,
  type TemplateDocument,
  type TemplateLayer,
  type TemplatePreviewData,
} from "@ecommerce-visual-workbench/templates";
import type Konva from "konva";
import {useEffect, useMemo, useRef, useState} from "react";
import {
  Arrow,
  Group,
  Image as KonvaImage,
  Layer,
  Line,
  Rect,
  Stage,
  Text,
  Transformer,
} from "react-konva";

export type EditorHistory = {
  past: TemplateDocument[];
  present: TemplateDocument;
  future: TemplateDocument[];
};

export function createEditorHistory(document: TemplateDocument): EditorHistory {
  return {past: [], present: document, future: []};
}

export function commitDocument(history: EditorHistory, document: TemplateDocument): EditorHistory {
  if (JSON.stringify(history.present) === JSON.stringify(document)) return history;
  return {past: [...history.past, history.present], present: document, future: []};
}

export function undoDocument(history: EditorHistory): EditorHistory {
  const previous = history.past.at(-1);
  if (!previous) return history;
  return {
    past: history.past.slice(0, -1),
    present: previous,
    future: [history.present, ...history.future],
  };
}

export function redoDocument(history: EditorHistory): EditorHistory {
  const next = history.future[0];
  if (!next) return history;
  return {
    past: [...history.past, history.present],
    present: next,
    future: history.future.slice(1),
  };
}

export function updateLayer(
  document: TemplateDocument,
  layerId: string,
  changes: Partial<TemplateLayer>,
): TemplateDocument {
  return {
    ...document,
    layers: document.layers.map((layer) => (layer.id === layerId ? {...layer, ...changes} : layer)),
  };
}

export function duplicateLayer(document: TemplateDocument, layerId: string): TemplateDocument {
  const source = document.layers.find((layer) => layer.id === layerId);
  if (!source) return document;
  const copy = {
    ...source,
    id: `${source.id}_copy_${document.layers.length + 1}`,
    x: source.x + 24,
    y: source.y + 24,
    zIndex: Math.max(0, ...document.layers.map((layer) => layer.zIndex)) + 1,
  };
  return {...document, layers: [...document.layers, copy]};
}

export function removeLayer(document: TemplateDocument, layerId: string): TemplateDocument {
  return {...document, layers: document.layers.filter((layer) => layer.id !== layerId)};
}

export function moveLayer(
  document: TemplateDocument,
  layerId: string,
  direction: "forward" | "backward",
): TemplateDocument {
  const ordered = [...document.layers].sort((left, right) => left.zIndex - right.zIndex);
  const index = ordered.findIndex((layer) => layer.id === layerId);
  const target = direction === "forward" ? index + 1 : index - 1;
  if (index < 0 || target < 0 || target >= ordered.length) return document;
  [ordered[index], ordered[target]] = [ordered[target], ordered[index]];
  const zIndex = new Map(ordered.map((layer, position) => [layer.id, position]));
  return {
    ...document,
    layers: document.layers.map((layer) => ({...layer, zIndex: zIndex.get(layer.id) ?? layer.zIndex})),
  };
}

function useRemoteImage(source?: string) {
  const [image, setImage] = useState<HTMLImageElement>();
  useEffect(() => {
    if (!source) {
      setImage(undefined);
      return;
    }
    const next = new window.Image();
    next.crossOrigin = "anonymous";
    next.onload = () => setImage(next);
    next.src = source;
    return () => {
      next.onload = null;
    };
  }, [source]);
  return image;
}

function ProductImage({layer, source, onSelect, onCommit}: CanvasLayerProps & {source?: string}) {
  const image = useRemoteImage(source);
  if (!image) {
    return (
      <Group onClick={onSelect}>
        <Rect {...rectProps(layer)} fill="#eef2f6" stroke="#b9c2cf" dash={[10, 8]} />
        <Text
          x={layer.x}
          y={layer.y + layer.height / 2 - 10}
          width={layer.width}
          text={layer.assetSource ?? "商品图片"}
          align="center"
          fill="#6f7b8e"
          fontSize={18}
        />
      </Group>
    );
  }
  const imageRatio = image.width / image.height;
  const frameRatio = layer.width / layer.height;
  const cover = layer.fit === "cover";
  const crop = cover
    ? imageRatio > frameRatio
      ? {x: (image.width - image.height * frameRatio) / 2, y: 0, width: image.height * frameRatio, height: image.height}
      : {x: 0, y: (image.height - image.width / frameRatio) / 2, width: image.width, height: image.width / frameRatio}
    : undefined;
  return (
    <KonvaImage
      image={image}
      {...rectProps(layer)}
      crop={crop}
      cornerRadius={layer.cornerRadius}
      draggable={!layer.locked}
      onClick={onSelect}
      onTap={onSelect}
      onDragEnd={(event) => onCommit({x: event.target.x(), y: event.target.y()})}
      onTransformEnd={(event) => transformed(event.target, layer, onCommit)}
    />
  );
}

type CanvasLayerProps = {
  layer: TemplateLayer;
  onSelect: () => void;
  onCommit: (changes: Partial<TemplateLayer>) => void;
};

function rectProps(layer: TemplateLayer) {
  return {
    id: layer.id,
    x: layer.x,
    y: layer.y,
    width: layer.width,
    height: layer.height,
    rotation: layer.rotation,
    opacity: layer.opacity,
    visible: layer.visible,
  };
}

function transformed(
  node: Konva.Node,
  layer: TemplateLayer,
  onCommit: (changes: Partial<TemplateLayer>) => void,
) {
  const scaleX = node.scaleX();
  const scaleY = node.scaleY();
  node.scaleX(1);
  node.scaleY(1);
  onCommit({
    x: node.x(),
    y: node.y(),
    width: Math.max(12, layer.width * scaleX),
    height: Math.max(12, layer.height * scaleY),
    rotation: node.rotation(),
  });
}

function CanvasNode(props: CanvasLayerProps & {preview: TemplatePreviewData}) {
  const {layer, preview, onSelect, onCommit} = props;
  const common = {
    ...rectProps(layer),
    draggable: !layer.locked,
    onClick: onSelect,
    onTap: onSelect,
    onDragEnd: (event: Konva.KonvaEventObject<DragEvent>) =>
      onCommit({x: event.target.x(), y: event.target.y()}),
    onTransformEnd: (event: Konva.KonvaEventObject<Event>) => transformed(event.target, layer, onCommit),
  };
  if (layer.type === "IMAGE") {
    return <ProductImage {...props} source={assetBindingUrl(layer, preview)} />;
  }
  if (layer.type === "TEXT") {
    return (
      <Text
        {...common}
        text={layer.text ?? ""}
        fill={layer.fill ?? "#172033"}
        fontSize={layer.fontSize ?? 32}
        fontFamily={layer.fontFamily ?? "Arial"}
        fontStyle={layer.fontWeight === "bold" ? "bold" : "normal"}
        align={layer.align}
        lineHeight={layer.lineHeight}
      />
    );
  }
  if (layer.type === "LINE") {
    const points = layer.points ?? [0, 0, layer.width, layer.height];
    const LineComponent = layer.arrowStart || layer.arrowEnd ? Arrow : Line;
    return (
      <LineComponent
        {...common}
        points={points}
        stroke={layer.stroke ?? "#172033"}
        strokeWidth={layer.strokeWidth ?? 2}
        dash={layer.dash}
        pointerAtBeginning={layer.arrowStart}
        pointerLength={12}
        pointerWidth={12}
      />
    );
  }
  if (layer.type === "GROUP") {
    return (
      <Group {...common}>
        {(layer.children ?? []).map((child) => (
          <CanvasNode key={child.id} layer={child} preview={preview} onSelect={onSelect} onCommit={() => undefined} />
        ))}
      </Group>
    );
  }
  return (
    <Rect
      {...common}
      fill={layer.fill ?? "#ffffff"}
      stroke={layer.stroke}
      strokeWidth={layer.strokeWidth}
      cornerRadius={layer.cornerRadius}
    />
  );
}

export function KonvaTemplateCanvas({
  document,
  canvasWidth,
  canvasHeight,
  background = "#ffffff",
  previewData,
  selectedLayerId,
  onSelectLayer,
  onChange,
  viewportWidth = 760,
}: {
  document: TemplateDocument;
  canvasWidth: number;
  canvasHeight: number;
  background?: string;
  previewData: TemplatePreviewData;
  selectedLayerId: string | null;
  onSelectLayer: (id: string | null) => void;
  onChange: (document: TemplateDocument) => void;
  viewportWidth?: number;
}) {
  const transformer = useRef<Konva.Transformer>(null);
  const stage = useRef<Konva.Stage>(null);
  const preview = useMemo(() => previewDocument(document, previewData), [document, previewData]);
  const scale = Math.min(1, viewportWidth / canvasWidth, 680 / canvasHeight);

  useEffect(() => {
    const node = selectedLayerId ? stage.current?.findOne(`#${selectedLayerId}`) : undefined;
    transformer.current?.nodes(node ? [node] : []);
    transformer.current?.getLayer()?.batchDraw();
  }, [selectedLayerId, preview]);

  return (
    <Stage
      ref={stage}
      width={canvasWidth * scale}
      height={canvasHeight * scale}
      scaleX={scale}
      scaleY={scale}
      onMouseDown={(event) => event.target === event.target.getStage() && onSelectLayer(null)}
      className="shadow-[0_24px_70px_rgba(23,32,51,.16)]"
    >
      <Layer>
        <Rect width={canvasWidth} height={canvasHeight} fill={background} listening={false} />
        {[...preview.layers]
          .sort((left, right) => left.zIndex - right.zIndex)
          .map((layer) => (
            <CanvasNode
              key={layer.id}
              layer={layer}
              preview={previewData}
              onSelect={() => !layer.locked && onSelectLayer(layer.id)}
              onCommit={(changes) => onChange(updateLayer(document, layer.id, changes))}
            />
          ))}
        <Transformer
          ref={transformer}
          rotateEnabled
          borderStroke="#ff6433"
          anchorFill="#ffffff"
          anchorStroke="#ff6433"
          anchorSize={12}
          boundBoxFunc={(oldBox, nextBox) =>
            nextBox.width < 12 || nextBox.height < 12 ? oldBox : nextBox
          }
        />
      </Layer>
    </Stage>
  );
}

export type TemplateGuide = {label: string; width: number; height: number; safeArea: number};

export function ImageTemplateEditor({guide}: {guide: TemplateGuide}) {
  const size = 360;
  const ratio = guide.width / guide.height;
  const frame = ratio >= 1 ? {width: size, height: size / ratio} : {width: size * ratio, height: size};
  const x = (420 - frame.width) / 2;
  const y = (420 - frame.height) / 2;
  const inset = Math.min(frame.width, frame.height) * guide.safeArea;
  return (
    <div className="overflow-hidden rounded-xl border border-[#dfe4ec] bg-[#e9edf4]">
      <Stage width={420} height={420} className="mx-auto max-w-full">
        <Layer>
          <Rect width={420} height={420} fill="#e9edf4" />
          <Rect x={x} y={y} width={frame.width} height={frame.height} fill="#fff" shadowBlur={18} shadowOpacity={0.08} />
          <Rect x={x + inset} y={y + inset} width={frame.width - inset * 2} height={frame.height - inset * 2} stroke="#ff6433" dash={[8, 6]} strokeWidth={2} />
          <Text x={18} y={18} text={guide.label.toUpperCase()} fill="#172033" fontSize={12} fontStyle="bold" fontFamily="Bahnschrift" letterSpacing={1.5} />
        </Layer>
      </Stage>
    </div>
  );
}
