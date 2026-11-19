import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Attendee } from "@/api/types";

type AttendeesFieldsProps = {
  attendees: Attendee[];
  onChange: (attendees: Attendee[]) => void;
};

export function AttendeesFields({ attendees, onChange }: AttendeesFieldsProps) {
  function updateAttendee(index: number, change: Partial<Attendee>) {
    onChange(attendees.map((attendee, i) => (i === index ? { ...attendee, ...change } : attendee)));
  }

  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-sm font-medium">Attendees</legend>
      {attendees.map((attendee, index) => (
        <div key={index} className="flex items-end gap-2 mt-2">
          <div className="flex flex-1 flex-col gap-1">
            <Label htmlFor={`attendee-${index}-name`}>Name</Label>
            <Input
              id={`attendee-${index}-name`}
              aria-label={`Attendee ${index + 1} name`}
              value={attendee.name}
              onChange={(event) => updateAttendee(index, { name: event.target.value })}
            />
          </div>
          <div className="flex flex-1 flex-col gap-1">
            <Label htmlFor={`attendee-${index}-company`}>Company</Label>
            <Input
              id={`attendee-${index}-company`}
              aria-label={`Attendee ${index + 1} company`}
              value={attendee.company}
              onChange={(event) => updateAttendee(index, { company: event.target.value })}
            />
          </div>
          <Button
            type="button"
            variant="ghost"
            onClick={() => onChange(attendees.filter((_, i) => i !== index))}
          >
            Remove
          </Button>
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="self-start mt-2"
        onClick={() => onChange([...attendees, { name: "", company: "" }])}
      >
        Add attendee
      </Button>
    </fieldset>
  );
}
