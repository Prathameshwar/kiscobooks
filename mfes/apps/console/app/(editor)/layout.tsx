/**
 * The full-bleed editor route group.
 *
 * Everything else in the console sits inside `ConsoleShell` — a rail, a topbar, a page
 * gutter. An editor cannot: the canvas needs the whole viewport, and a page that scrolls
 * takes the toolbar away from the hand using it. This group therefore renders outside the
 * shell while staying a console route, so a user still reaches the designer by navigating
 * rather than by changing origin.
 *
 * It adds the two designer stylesheets to the root layout's list — the canvas scale and
 * the editor chrome. They load only for this group, which keeps 40 inspector-row rules out
 * of every form page's stylesheet.
 */
import '@janso/ui/styles/canvas-tokens.css';
import '@janso/ui/styles/designer.css';

export default function EditorLayout({ children }: { children: React.ReactNode }) {
  return children;
}
