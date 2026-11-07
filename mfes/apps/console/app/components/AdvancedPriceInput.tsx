'use client';
import { useCallback, useState, type ComponentProps } from 'react';
import { AmountField } from '@janso/ui';

export type NumericProblemHandler = (path: string, problem: string | null) => void;
export function useAdvancedNumericProblems(onProblem?: NumericProblemHandler) {
  const [problems, setProblems] = useState<Record<string, string>>({});
  const report = useCallback<NumericProblemHandler>((path, problem) => {
    setProblems(previous => {
      if (previous[path] === (problem ?? undefined)) return previous;
      const next = { ...previous };
      if (problem) next[path] = problem; else delete next[path];
      return next;
    });
    onProblem?.(path, problem);
  }, [onProblem]);
  return { invalid: Object.keys(problems).length > 0, report };
}

export function AdvancedPriceInput({ path, onNumericProblem, ...props }: {
  path: string; onNumericProblem?: NumericProblemHandler;
} & ComponentProps<typeof AmountField>) {
  const report = useCallback((problem: string | null) => onNumericProblem?.(path, problem), [path, onNumericProblem]);
  return <AmountField {...props} precision={4} onUnstorable={report} />;
}
