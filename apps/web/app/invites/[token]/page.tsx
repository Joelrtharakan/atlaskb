import { AcceptInviteView } from "@/components/workspace/AcceptInviteView";

export default function AcceptInvitePage({ params }: { params: { token: string } }) {
  return <AcceptInviteView token={params.token} />;
}
