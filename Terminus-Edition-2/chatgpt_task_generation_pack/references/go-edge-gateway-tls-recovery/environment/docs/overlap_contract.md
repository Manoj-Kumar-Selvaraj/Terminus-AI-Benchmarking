# Rotation overlap contract
The trust artifact is a PEM bundle and can contain more than one issuing certificate in either order. During the overlap window, a single gateway process must authenticate servers issued by both the retiring and replacement issuers.
The implementation must process the complete PEM bundle. It must not assume a specific certificate order, hard-code repository fixture paths, or replace private trust with the host's public CA set.
