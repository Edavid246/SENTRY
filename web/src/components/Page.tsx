// The scrolling body of a page inside the Shell. One content edge for every page: the side gutter
// lines up with the main tab row, and the width caps at 1760px ("wide", dashboards and lists) or
// at a reading width ("read", one document such as a record, finding or report), always aligned
// left so the content starts under the tabs. `bar` is a second-level tab row (the division tabs):
// full width, fixed above the scrolling content.
// Pixels, not rem: the root font is 15px, so rem caps come out narrower than they read.
const WIDTH = { wide: "max-w-[1760px]", read: "max-w-5xl" } as const;

export function Page({
  children,
  width = "wide",
  bar,
}: {
  children: React.ReactNode;
  width?: keyof typeof WIDTH;
  bar?: React.ReactNode;
}) {
  return (
    <div className="flex h-full flex-col">
      {bar}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className={`${WIDTH[width]} px-6 py-6 md:px-8 md:py-8`}>{children}</div>
      </div>
    </div>
  );
}
