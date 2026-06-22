import { Info } from "lucide-react";

export default function OmPage() {
  return (
    <div className="min-h-screen bg-[#F5F3EF] flex items-center justify-center">
      <div className="text-center">
        <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-[#EDE9E2] mx-auto mb-4">
          <Info size={20} strokeWidth={1.75} className="text-[#ADA9A2]" />
        </div>
        <p className="text-[13px] font-semibold text-[#111110]">Om TippeQpongen</p>
        <p className="text-[12px] text-[#ADA9A2] mt-1">Under planlegging</p>
      </div>
    </div>
  );
}
