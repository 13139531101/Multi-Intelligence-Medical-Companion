import React from 'react';
import EventItem from './EventItem';

function EventList({ events }) {
  if (!events || events.length === 0) {
    return <p className="text-gray-600">No events for this conversation.</p>;
  }

  return (
    <div className="space-y-4">
      {events.map(event => (
        <EventItem key={event.id} event={event} />
      ))}
    </div>
  );
}

export default EventList;